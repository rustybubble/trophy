"""Run a trained serve spotter on one or two videos, exporting reviewable events."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from trophy.serves.inference import analyze_session


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--config',required=True);p.add_argument('--output',required=True)
    p.add_argument('--checkpoint',default='weights/serves/table-tennis-final.pt')
    p.add_argument('--device',choices=['auto','mps','cpu','cuda'],default='auto')
    p.add_argument('--threshold',type=float);p.add_argument('--max-seconds',type=float,default=600.)
    a=p.parse_args()
    def progress(view,stage,done,total):
        if done%10==0 or done==total:print(f'{view}: {stage} {done}/{total}',flush=True)
    result=analyze_session(a.config,a.output,a.checkpoint,device=a.device,threshold=a.threshold,max_seconds=a.max_seconds,progress=progress)
    for path in (ROOT/'web/serves').glob('*'):
        if path.is_file():shutil.copy2(path,Path(a.output)/path.name)
    print(json.dumps(dict(events=len(result['events']),device=result['device'],output=str(Path(a.output).resolve()),
                          processing_seconds=result['processing_seconds']),indent=2))
