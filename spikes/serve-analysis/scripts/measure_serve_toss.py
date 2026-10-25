"""Reproduce a rule-linked toss evidence bundle from saved frame annotations."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from trophy.serves.legality import analyze_toss

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--session',help='Session JSON; optional for a complete exported evidence bundle')
    p.add_argument('--annotations',required=True,help='Frame annotations or exported toss-evidence JSON')
    p.add_argument('--calibration');p.add_argument('--output',required=True)
    a=p.parse_args()
    read=lambda path:json.loads(Path(path).read_text())
    bundle=read(a.annotations)
    request=bundle.get('annotations',bundle)
    session=read(a.session) if a.session else bundle.get('source_session')
    if session is None:p.error('--session is required when the input contains only frame annotations')
    calibration=read(a.calibration) if a.calibration else bundle.get('calibration')
    result=analyze_toss(session,request,calibration)
    Path(a.output).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result['decision'],indent=2))
