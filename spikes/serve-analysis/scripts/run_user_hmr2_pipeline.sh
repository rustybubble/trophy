#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Downloading runs separately so completed ranges survive transient disconnects.
while ! .venv/bin/python - <<'PY'
from pathlib import Path
raise SystemExit(0 if Path('weights/hmr2_data.tar.gz').stat().st_size == 2710589440 else 1)
PY
do
  sleep 10
done

.venv/bin/python - <<'PY'
import hashlib,json,tarfile
from pathlib import Path
archive=Path('weights/hmr2_data.tar.gz');destination=Path('weights/hmr2-assets')
with tarfile.open(archive,'r:*') as tar:
    members=[m for m in tar.getmembers() if m.isfile() and (m.name.endswith('.ckpt') or m.name.endswith('model_config.yaml') or m.name in ['data/smpl_mean_params.npz','data/SMPL_to_J19.pkl'])]
    tar.extractall(destination,members=members,filter='data')
checkpoint=next(destination.rglob('*.ckpt'))
with checkpoint.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
expected='c9ea09c834161468638c9de7a782c614e300c622709bf52967274c543ec72fcf'
if digest!=expected:raise ValueError('Official model checkpoint checksum mismatch: '+digest)
metadata=dict(source='https://www.cs.utexas.edu/~pavlakos/4dhumans/hmr2_data.tar.gz',checkpoint=str(checkpoint),checkpoint_sha256=digest,source_commit='efe18deff163b29dff87ddbd575fa29b716a356c')
(destination/'provenance.json').write_text(json.dumps(metadata,indent=2));print(json.dumps(metadata),flush=True)
PY

if [ ! -f artifacts/user-two-camera/hmr2/smoke-camera1/predictions.npz ]; then
  .venv-hmr2/bin/python scripts/run_hmr2.py --video artifacts/user-two-camera/camera1-8s-14s.mp4 --poses artifacts/user-two-camera/hmr2/poses-camera1.json --output artifacts/user-two-camera/hmr2/smoke-camera1 --max-frames 2 --batch-size 2
fi
for view in 1 2; do
  if [ ! -f "artifacts/user-two-camera/hmr2/inference-camera${view}/predictions.npz" ]; then
    .venv-hmr2/bin/python scripts/run_hmr2.py --video "artifacts/user-two-camera/camera${view}-8s-14s.mp4" --poses "artifacts/user-two-camera/hmr2/poses-camera${view}.json" --output "artifacts/user-two-camera/hmr2/inference-camera${view}"
  fi
done
.venv-hmr2/bin/python scripts/fit_hmr2_multiview.py
.venv-hmr2/bin/python scripts/render_hmr2_replay.py
printf '%s\n' 'HMR2 reconstruction pipeline complete'
