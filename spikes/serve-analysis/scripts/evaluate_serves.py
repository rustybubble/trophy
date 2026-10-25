"""Evaluate exported events against separately authored event annotations."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from trophy.serves.events import evaluate_events


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--predictions',required=True);p.add_argument('--truth',required=True)
    p.add_argument('--output',required=True);p.add_argument('--tolerance',type=float,default=.35)
    a=p.parse_args();prediction=json.loads(Path(a.predictions).read_text());truth=json.loads(Path(a.truth).read_text())
    interval=truth.get('annotation_scope_seconds',[0,float('inf')])
    events=[e for e in prediction['events'] if interval[0]<=e['time_seconds']<=interval[1] and e['event_status']!='rejected']
    expected=[e for e in truth['events'] if interval[0]<=e['time_seconds']<=interval[1]]
    metrics=evaluate_events(events,expected,a.tolerance)
    duration=interval[1]-interval[0]
    metrics.update(scope_seconds=interval,annotated_serves=len(expected),predicted_candidates=len(events),
                   false_candidates_per_hour=metrics['false_positives']/(duration/3600) if duration>0 else None,
                   annotation_source=truth.get('annotation_source'),
                   annotations_used_for_training=truth.get('used_for_training'),
                   limitations=truth.get('limitations',[]))
    Path(a.output).write_text(json.dumps(metrics,indent=2,allow_nan=False));print(json.dumps(metrics,indent=2))
