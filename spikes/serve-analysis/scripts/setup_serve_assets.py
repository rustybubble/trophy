"""Fetch pinned public annotations and the verified E2E-Spot initialization."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
DATA_COMMIT='36471a76b969a0340df59258a813bf8214e68e7c'
MODEL_COMMIT='10d07a4fb01f2eb76785e15552e5648bf0793509'
INITIALIZATION_SHA256='5949e3e869f20480f51d89c68514b3eda4399779d9d2ca20c9b78344b11c8e2c'
ANNOTATIONS={
 'train/game_1.json':'9b1ef7cc51343bb1a000b660c71c6a60d076e687',
 'train/game_2.json':'dec70e48b9f740344396bc7705d6086281157582',
 'train/game_3.json':'a273e06b453c30321ffafff4d4f5856d89a0cf46',
 'train/game_4.json':'6a447369b3e8a8c63988c04352d57226e3b9ef0b',
 'train/game_5.json':'402f8c4274c0d213deda3b991996b84ed594673e',
 'test/test_1.json':'6b40334c921dcb27cede76428dcf2775ad541bca',
 'test/test_2.json':'b15af2e54b6922b7d648a2137ebfba315a6f7696',
 'test/test_3.json':'ab6333c0af21e4972e0006c62c07623691d8d459',
 'test/test_4.json':'c639950e0b576059e60df31950f3b2ab72073afd',
 'test/test_5.json':'043154a2b715d38ea6747537469546f4bc53dd86',
 'test/test_6.json':'ebe3efc722e8d41b64e10be2d7063a37413364d3',
 'test/test_7.json':'5dd95c5e83e6b8837021cd75271b0f9d17d035fd'}


def download(url,path,verify):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and verify(path.read_bytes()):return
    request=urllib.request.Request(url,headers={'User-Agent':'Trophy-Serve-Spotter/1'})
    with urllib.request.urlopen(request,timeout=120) as response:data=response.read()
    if not verify(data):raise ValueError(f'Upstream checksum changed: {url}')
    temporary=path.with_suffix('.download');temporary.write_bytes(data);temporary.replace(path)


def setup(annotations=True):
    download(f'https://raw.githubusercontent.com/jhong93/e2e-spot-models/{MODEL_COMMIT}/tennis_rny002gsm_gru_rgb/checkpoint_040.pt',
             ROOT/'weights/serves/tennis-initialization.pt',lambda data:hashlib.sha256(data).hexdigest()==INITIALIZATION_SHA256)
    if annotations:
        def annotation(item):
            name,expected=item
            download(f'https://raw.githubusercontent.com/moamal01/table_tennis_data/{DATA_COMMIT}/data/raw/game_data/{name}',
                     ROOT/'artifacts/serves-data/annotations'/name,
                     lambda data:hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()==expected)
        with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(annotation,ANNOTATIONS.items()))
    print('Verified published initialization and requested annotation assets.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--initialization-only',action='store_true');a=p.parse_args()
    setup(not a.initialization_only)
