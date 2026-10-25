"""Fetch checksum-pinned, real two-view TT3D samples from the authors' server."""
import argparse,hashlib,json
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
REMOTE={
 'samples/tt3d/game_00/side-010.mp4':'side/game_00/010.mp4',
 'samples/tt3d/game_00/oblique-010.mp4':'oblique/game_00/010.mp4',
 'samples/tt3d/game_00/side.yaml':'side/game_00_table_pose.yaml',
 'samples/tt3d/game_00/oblique.yaml':'oblique/game_00_table_pose.yaml',
 'samples/tt3d/game_00/reference-010.csv':'3d_tracking/game_00/010.csv',
 'samples/tt3d/game_00/038/side.mp4':'side/game_00/038.mp4',
 'samples/tt3d/game_00/038/oblique.mp4':'oblique/game_00/038.mp4',
 'samples/tt3d/game_00/038/reference.csv':'3d_tracking/game_00/038.csv',
}


def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-only',action='store_true');a=p.parse_args()
    manifest=json.loads((ROOT/'configs/tt3d-assets.json').read_text())
    for item in manifest['files']:
        path=ROOT/item['path'];expected=item['sha256']
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==expected:
            print('Verified',item['path']);continue
        if a.verify_only:raise ValueError(f'Missing or checksum mismatch: {path}')
        path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix(path.suffix+'.part')
        with requests.get('https://cloud.cs.uni-tuebingen.de/public.php/webdav/'+REMOTE[item['path']],
                          auth=('SCKq85JZEmKoC6J',''),stream=True,timeout=(20,120)) as response:
            response.raise_for_status()
            with temp.open('wb') as f:
                for chunk in response.iter_content(1024*1024):f.write(chunk)
        if hashlib.sha256(temp.read_bytes()).hexdigest()!=expected:
            raise ValueError(f'Official download checksum changed: {path}; retained .part for inspection')
        temp.replace(path);print('Downloaded and verified',item['path'])

if __name__=='__main__':main()
