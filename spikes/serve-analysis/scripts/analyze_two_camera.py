"""Run the combined two-angle workflow from a saved upload configuration."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trophy.session import analyze_two_camera

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    def progress(stage, detail):
        print(f'{stage}: {detail.splitlines()[-1] if detail else ""}', flush=True)
    print(json.dumps(analyze_two_camera(args.config, args.output, progress), indent=2))
