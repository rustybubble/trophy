"""Download only timestamped training windows using HTTP range video decoding.

No 5 GB source video is saved. Public annotations are separately pinned/downloaded
by setup_serve_assets.py. Whole source videos, not adjacent frames, define splits.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import sys
import time
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from trophy.serves.data import read_samples, read_events


def prepare(output, max_serves=30, workers=4):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    records = []
    rng = np.random.default_rng(20261024)
    for annotation in sorted((output / 'annotations').glob('*/*.json')):
        video = annotation.stem
        split = 'train' if video in ['game_1', 'game_2', 'game_3'] else ('val' if video == 'game_4' else 'test')
        events = read_events(annotation)
        serves = [e for e in events if e['kind'] == 'serve']
        if not serves:
            continue
        if len(serves) > max_serves:
            serves = [serves[i] for i in np.linspace(0, len(serves)-1, max_serves).round().astype(int)]
        strokes = [e for e in events if e['kind'] == 'stroke' and
                   all(abs(e['time']-s['time']) > 1.8 for s in events if s['kind']=='serve')]
        if len(strokes) > len(serves):
            strokes = [strokes[i] for i in rng.choice(len(strokes), len(serves), replace=False)]
        # Sample non-contact windows as negatives, keeping them away from all
        # annotated stroke contacts. They may include ordinary waiting/handling.
        background = []
        for t in rng.uniform(2, max(e['time'] for e in events)-2, 1000):
            if all(abs(t-e['time']) > 2. for e in events):
                background.append(dict(time=float(t), kind='background'))
                if len(background) >= len(serves):
                    break
        for index, anchor in enumerate(serves + strokes + background):
            # Contact occurs away from a fixed centre to avoid learning the window position.
            start = max(0., anchor['time'] - float(rng.uniform(1.3, 2.4)))
            key = f'{video}-{index:04d}'
            records.append(dict(id=key, video_id=video, split=split, start=start, end=start+3.2,
                                anchor=anchor, events=[e for e in events if start <= e['time'] < start+3.2],
                                source=f'https://lab.osai.ai/datasets/openttgames/data/{video}.mp4',
                                path=f'clips/{key}.npz'))
    (output / 'clips').mkdir(exist_ok=True)

    def extract(record):
        target = output / record['path']
        if target.exists():
            try:
                with np.load(target) as cached:
                    if len(cached['images']) != len(cached['times']):
                        raise ValueError('Incomplete cached window')
                    times=cached['times']
                    if not len(times) or times[0]<record['start']-.02 or times[0]>record['start']+.15 or times[-1]>=record['end']+.02:
                        raise ValueError('Cached window belongs to another sampling interval')
            except (ValueError, OSError, EOFError, zipfile.BadZipFile):
                target.unlink()
        if not target.exists():
            for attempt in range(3):
                try:
                    images, times = read_samples(record['source'], record['start'], record['end'])
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(attempt+1)
            if len(images) < 40:
                raise ValueError(f'Incomplete training window {record["id"]}: {len(images)} frames')
            temporary = target.with_suffix('.partial.npz')
            np.savez_compressed(temporary, images=images, times=times)
            temporary.replace(target)
        record['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
        return record

    completed = []
    errors = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(extract, r): r for r in records}
        for future in as_completed(futures):
            record = futures[future]
            try:
                completed.append(future.result())
            except Exception as exc:
                errors.append(dict(id=record['id'], reason=str(exc)))
            if (len(completed)+len(errors)) % 10 == 0:
                print(f'Prepared {len(completed)}/{len(records)} windows; errors={len(errors)}', flush=True)
            # Persist useful progress if a long acquisition is interrupted.
            (output / 'manifest.json').write_text(json.dumps(dict(
                version=1, dataset='Extended OpenTTGames', license='CC BY-NC-SA 4.0',
                annotation_commit='36471a76b969a0340df59258a813bf8214e68e7c',
                source_fps=120, sampling_fps=15, image_size=[224,128],
                records=sorted(completed,key=lambda r:r['id']), errors=errors), indent=2))
    print(json.dumps(dict(windows=len(completed), errors=errors), indent=2))
    if errors:
        raise RuntimeError('Some training windows failed; rerun to retry cached acquisition')


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default='artifacts/serves-data')
    p.add_argument('--max-serves',type=int,default=30);p.add_argument('--workers',type=int,default=4)
    a=p.parse_args();prepare(a.output,a.max_serves,a.workers)
