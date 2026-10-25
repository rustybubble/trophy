"""Resume the official HMR2 archive using verified HTTP byte ranges."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import time
import requests

URL = 'https://www.cs.utexas.edu/~pavlakos/4dhumans/hmr2_data.tar.gz'
SIZE = 2710589440
TARGET = Path('weights/hmr2_data.tar.gz')
PARTS = Path('weights/hmr2-range-parts')
CHUNK = 16 * 1024 * 1024


def main():
    PARTS.mkdir(exist_ok=True)
    manifest = PARTS / 'manifest.json'
    if manifest.exists():
        start = json.loads(manifest.read_text())['prefix_bytes']
    else:
        start = TARGET.stat().st_size if TARGET.exists() else 0
        manifest.write_text(json.dumps(dict(url=URL, total_bytes=SIZE,
                                            prefix_bytes=start, chunk_bytes=CHUNK)))
    ranges = [(lo, min(SIZE - 1, lo + CHUNK - 1)) for lo in range(start, SIZE, CHUNK)]

    def fetch(bounds):
        low, high = bounds
        path = PARTS / f'{low:012d}-{high:012d}.part'
        expected = high - low + 1
        if path.exists() and path.stat().st_size == expected:
            return path
        error = None
        for attempt in range(20):
            try:
                have = path.stat().st_size if path.exists() else 0
                if have == expected:
                    return path
                if have > expected:
                    path.write_bytes(b'')
                    have = 0
                resume = low + have
                with requests.get(URL, headers={'Range': f'bytes={resume}-{high}'},
                                  stream=True, timeout=(20, 40)) as response:
                    response.raise_for_status()
                    if response.status_code != 206 or response.headers.get('Content-Range') != f'bytes {resume}-{high}/{SIZE}':
                        raise ValueError('Server did not honor the exact requested range')
                    with path.open('ab') as output:
                        for chunk in response.iter_content(1024 * 1024):
                            output.write(chunk)
                if path.stat().st_size != expected:
                    raise ValueError('Incomplete range download')
                return path
            except (OSError, ValueError, requests.RequestException) as exc:
                error = exc
                time.sleep(min(2 ** attempt, 8))
        raise RuntimeError(f'Range {low}-{high} failed: {error}')

    done = 0
    print(f'Resuming {start}/{SIZE} bytes; {len(ranges)} ranges', flush=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        for future in as_completed([pool.submit(fetch, r) for r in ranges]):
            path = future.result()
            done += path.stat().st_size
            print(f'Fetched {start+done}/{SIZE} bytes', flush=True)
    # Truncate to the original prefix so repeated assembly is safe after interruption.
    with TARGET.open('r+b' if TARGET.exists() else 'wb') as output:
        output.truncate(start)
        output.seek(start)
        for low, high in ranges:
            with (PARTS / f'{low:012d}-{high:012d}.part').open('rb') as source:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
    if TARGET.stat().st_size != SIZE:
        raise ValueError('Final archive size mismatch')
    print('Official archive download complete', flush=True)


if __name__ == '__main__':
    main()
