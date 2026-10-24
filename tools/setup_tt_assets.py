#!/usr/bin/env python3
"""Verify/copy existing approved model assets to ignored local weights storage.

No network downloads or redistribution. Public BlurBall use remains an explicit
user decision because checkpoint licensing is not established by its code MIT.
"""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = {
    "blurball_best": (
        "3545206c7155194ea654899d33579c88c9fd8e82c632cbdbae3b0c0ec3f2985f",
        "BlurBall official checkpoint; license unstated; private evaluation only",
    ),
    "pose_landmarker_full.task": (
        "5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1",
        "Official MediaPipe Pose Full float16 v1",
    ),
    "hand_landmarker.task": (
        "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1",
        "Official MediaPipe Hand Full float16 v1",
    ),
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--from-directory", type=Path, required=True)
    a = p.parse_args()
    out = ROOT / "weights"
    out.mkdir(exist_ok=True)
    manifest = json.loads((out / "manifest.json").read_text()) if (out / "manifest.json").exists() else []
    for name, (expected, note) in ASSETS.items():
        source = a.from_directory / name
        if not source.exists():
            continue
        actual = hashlib.sha256(source.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Unexpected checkpoint: {name}")
        target = out / name
        if source.resolve() != target.resolve():
            shutil.copyfile(source, target)
        manifest = [row for row in manifest if row["file"] != name]
        manifest.append(dict(file=name, sha256=actual, note=note, source=str(source.resolve())))
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
