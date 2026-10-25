"""Explicit manual development labels for the first 73 s of the room recording.

Later room serves are excluded from training. Both source views of each labeled
physical event belong to the same development split. Source labels are visible
and separate from the inference path; they are never injected as detections.
"""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from trophy.serves.data import cached_samples


def prepare():
    data=ROOT/'artifacts/serves-data'
    original=json.loads((data/'manifest.json').read_text())
    cfg=json.loads((ROOT/'configs/serve-user-two-camera.json').read_text())
    records=[]
    # These two contact annotations precede inspection of the model outputs.
    event_times=[7.77,18.83]
    starts=[5.7,6.1,6.5,16.6,17.,17.4]
    negative_starts=[0.,2.4,8.5,11.,13.,19.2,23.,26.,30.,34.,38.,42.,46.,50.,54.,58.,62.,66.,69.5]
    for index,view in enumerate(cfg['views']):
        images,times=cached_samples(view['video'],107.,ROOT/'artifacts/serve-sample-cache')
        offset=view['source_offset_seconds']
        side='left' if index==0 else 'right'
        for j,start in enumerate(starts+negative_starts):
            source_start=start+offset;mask=(times>=source_start)&(times<source_start+3.2)
            if mask.sum()<40:raise ValueError('Incomplete local example')
            key=f'room-development-view{index+1}-{j:03d}'
            target=data/'clips'/f'{key}.npz'
            np.savez_compressed(target,images=images[mask],times=times[mask])
            events=[dict(time=t+offset,kind='serve',side=side) for t in event_times if start<=t<start+3.2]
            records.append(dict(id=key,video_id='room-development-0-73s',split='train',
                                source=view['video'],path=f'clips/{key}.npz',start=source_start,end=source_start+3.2,
                                anchor=dict(kind='serve' if events else 'background'),events=events,
                                annotation_source='manual visible development labels',
                                sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    manifest=dict(original,records=original['records']+records,
                  dataset='Extended OpenTTGames + explicit room development examples',
                  local_training_interval_seconds=[0,73],local_holdout_interval_seconds=[73,107],
                  local_holdout_warning='Temporal holdout within the same session; not an independent camera/player benchmark')
    (data/'adaptation-manifest.json').write_text(json.dumps(manifest,indent=2))
    print(f'Prepared {len(records)} explicit local development windows; later serves excluded.')


if __name__=='__main__':prepare()
