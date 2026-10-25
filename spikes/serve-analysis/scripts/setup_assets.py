#!/usr/bin/env python3
"""Fetch only pinned public author-released assets, with SHA-256 verification."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
COMMIT = '2f0f5496f7ba4b5b1a36790749935121b2ce972d'
ASSETS = {
    'heldout': dict(url='https://cloud.cs.uni-tuebingen.de/public.php/webdav/22/rallies_videos/003.mp4',
                    public_share='C3pJEPKWQAkono7', path='samples/official-22-003.mp4',
                    sha256='3597a95c664683d4b512c934b095bf51b45eda9112ebf377c960742e2146e011'),
    'annotations': dict(url='https://cloud.cs.uni-tuebingen.de/public.php/webdav/all_csv_midpoint_annotations.zip',
                        public_share='C3pJEPKWQAkono7', path='samples/official-midpoint-annotations.zip',
                        sha256='74ea49d3ce1a27f09edf1e3525348ac717e50f8f024f226baec941026237faf7'),
    'source': dict(url=f'https://codeload.github.com/cogsys-tuebingen/blurball/tar.gz/{COMMIT}',
                   sha256='34613ff1158731c4bdcafe828375195fa43ceb796c15b4d9d85ce0951d10a289'),
    'weights': dict(url='https://cloud.cs.uni-tuebingen.de/public.php/webdav/blurball_best',
                    public_share='6Z8TpM3sXRKHzGC', path='weights/blurball_best',
                    sha256='3545206c7155194ea654899d33579c88c9fd8e82c632cbdbae3b0c0ec3f2985f'),
    'sample': dict(url='https://cloud.cs.uni-tuebingen.de/public.php/webdav/00/rallies_videos/001.mp4',
                   public_share='C3pJEPKWQAkono7', path='samples/official-00-001.mp4',
                   sha256='6d0633f8dabf93fa50df7e9d3280fde27cebee858f8af1c10085d5af6fb0e972'),
}


def checksum(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def download(asset, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and checksum(dest) == asset['sha256']:
        print(f'Verified {dest}')
        return
    headers = {'User-Agent': 'Trophy-BlurBall-validation/0.1'}
    if asset.get('public_share'):
        headers['Authorization'] = 'Basic ' + base64.b64encode((asset['public_share'] + ':').encode()).decode()
    request = urllib.request.Request(asset['url'], headers=headers)
    partial = dest.with_suffix('.download')
    try:
        print(f'Downloading {asset["url"]}', flush=True)
        with urllib.request.urlopen(request, timeout=120) as response, partial.open('wb') as f:
            shutil.copyfileobj(response, f)
        if checksum(partial) != asset['sha256']:
            raise ValueError(f'Checksum mismatch for {dest}; the upstream asset may have changed.')
        partial.replace(dest)
    finally:
        partial.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sample', action='store_true', help='Also obtain the small real official rally')
    args = parser.parse_args()
    source = ROOT / 'vendor/blurball'
    if not source.exists():
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'source.tar.gz'
            download(ASSETS['source'], archive)
            with tarfile.open(archive) as tar:
                tar.extractall(Path(tmp) / 'unpack', filter='data')
            extracted = Path(tmp) / 'unpack' / f'blurball-{COMMIT}'
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(extracted, source)
    else:
        manifest = json.loads((ROOT / 'vendor/UPSTREAM.json').read_text())
        for name, expected in manifest['files_sha256'].items():
            if not (source / name).is_file() or checksum(source / name) != expected:
                raise ValueError(f'Vendored source differs from pinned snapshot: {name}')
        print('Verified pinned, unmodified upstream source.')
    for name in ['weights'] + (['sample', 'heldout', 'annotations'] if args.sample else []):
        asset = ASSETS[name]
        download(asset, ROOT / asset['path'])
    if args.sample:
        with zipfile.ZipFile(ROOT / ASSETS['annotations']['path']) as z:
            for scene, clip in [('00', '001'), ('22', '003')]:
                data = z.read(f'all_csv_annotations/{scene}_csv_{clip}.csv')
                (ROOT / f'samples/official-{scene}-{clip}.csv').write_bytes(data)
    print('Assets ready.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Setup failed: {exc}', file=sys.stderr)
        sys.exit(1)
