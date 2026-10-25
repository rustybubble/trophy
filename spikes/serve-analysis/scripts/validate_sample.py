"""Evaluate exported predictions against the official per-frame midpoint labels.

This is a small clip check, not a reproduction of the paper's benchmark.
"""
import argparse
import csv
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from PIL import Image, ImageDraw

p = argparse.ArgumentParser()
p.add_argument('--output', required=True)
p.add_argument('--labels', required=True)
p.add_argument('--video', required=True)
p.add_argument('--label-width', type=int, default=1280)
p.add_argument('--label-height', type=int, default=720)
a = p.parse_args()
out = Path(a.output)
rows = json.loads((out / 'detections.json').read_text())
report = json.loads((out / 'report.json').read_text())
labels = {int(r['Frame']): r for r in csv.DictReader(open(a.labels))}
w, h = report['source']['width'], report['source']['height']
sx, sy = w / a.label_width, h / a.label_height
errors, details = [], []
tp = fp = fn = tn = 0
for r in rows:
    gt = labels.get(r['frame_index'])
    if gt is None:
        raise ValueError('Missing official frame label')
    visible = bool(int(gt['Visibility']))
    distance = None
    if visible and r['detected']:
        distance = float(np.hypot(r['x'] - float(gt['X']) * sx, r['y'] - float(gt['Y']) * sy))
        errors.append(distance)
        if distance <= 10:
            tp += 1
        else:
            fp += 1
            fn += 1
    elif visible:
        fn += 1
    elif r['detected']:
        fp += 1
    else:
        tn += 1
    details.append(dict(frame_index=r['frame_index'], gt_visible=visible,
                        detected=r['detected'], localization_error_px=distance))
summary = dict(frames=len(rows), label_frames=len(labels), labels=str(Path(a.labels).resolve()),
               label_coordinate_resolution=[a.label_width, a.label_height],
               prediction_resolution=[w, h], matching_tolerance_px=10,
               true_positive=tp, false_positive=fp, false_negative=fn, true_negative=tn,
               precision_at_10px=tp / (tp + fp) if tp + fp else None,
               recall_at_10px=tp / (tp + fn) if tp + fn else None,
               median_error_on_visible_detected_px=float(np.median(errors)) if errors else None,
               p95_error_on_visible_detected_px=float(np.percentile(errors, 95)) if errors else None,
               max_error_on_visible_detected_px=max(errors) if errors else None,
               error_over_10px_frames=[d['frame_index'] for d in details if d['localization_error_px'] is not None and d['localization_error_px'] > 10],
               missed_visible_frames=[d['frame_index'] for d in details if d['gt_visible'] and not d['detected']],
               false_visible_frames=[d['frame_index'] for d in details if not d['gt_visible'] and d['detected']],
               notes=['10px tolerance applies in source pixels. Wrong location counts as both FP and FN.',
                      'Official labels may themselves contain errors/occlusions. Metrics assume frame zero aligns with original released MP4.',
                      'Review contact sheet plus video; this small clip is not a general accuracy estimate.'])
(out / 'label_validation.json').write_text(json.dumps(summary, indent=2))
(out / 'label_errors.json').write_text(json.dumps(details, indent=2))
# Sample the beginning, middle, end and largest errors for human inspection.
selected = set(np.linspace(0, len(rows) - 1, 9).round().astype(int).tolist())
selected.update([d['frame_index'] for d in sorted(details, key=lambda d: d['localization_error_px'] or 0, reverse=True)[:3]])
selected = sorted(selected)
cap = cv2.VideoCapture(a.video)
tiles = []
for index in selected:
    cap.set(cv2.CAP_PROP_POS_FRAMES, index)
    ok, frame = cap.read()
    if not ok:
        raise RuntimeError('Cannot read validation frame')
    gt, r = labels[index], rows[index]
    if int(gt['Visibility']):
        cv2.drawMarker(frame, (round(float(gt['X']) * sx), round(float(gt['Y']) * sy)),
                       (255, 0, 255), cv2.MARKER_CROSS, 20, 2)
    if r['detected']:
        cv2.circle(frame, (round(r['x']), round(r['y'])), 10, (0, 255, 0), 2)
    tile = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).resize((640, 360))
    panel = Image.new('RGB', (640, 390), '#171b24')
    panel.paste(tile, (0, 30))
    detail = details[index]
    err = detail['localization_error_px']
    ImageDraw.Draw(panel).text((8, 8), f'Frame {index} | green=prediction magenta=official label | error={err:.1f}px' if err is not None else f'Frame {index} | detected={r["detected"]} GT visible={detail["gt_visible"]}', fill='white')
    tiles.append(panel)
cap.release()
sheet = Image.new('RGB', (1280, 390 * ((len(tiles) + 1) // 2)), '#171b24')
for i, tile in enumerate(tiles):
    sheet.paste(tile, (i % 2 * 640, i // 2 * 390))
sheet.save(out / 'validation-contact-sheet.jpg', quality=92)
print(json.dumps(summary, indent=2))
