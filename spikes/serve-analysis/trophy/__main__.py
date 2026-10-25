import argparse
import json
import sys
from .model import DEFAULT_WEIGHTS
from .pipeline import analyze


def main():
    parser = argparse.ArgumentParser(description='Pretrained BlurBall clip analysis, locally on MPS or CPU')
    parser.add_argument('video')
    parser.add_argument('--output', required=True, help='New or empty output directory')
    parser.add_argument('--weights', default=str(DEFAULT_WEIGHTS))
    parser.add_argument('--device', choices=['auto', 'mps', 'cpu'], default='auto')
    parser.add_argument('--threshold', type=float, default=.7)
    parser.add_argument('--max-frames', type=int, default=600)
    parser.add_argument('--max-duration', type=float)
    parser.add_argument('--photometric', choices=['rgb', 'max-channel-gray'], default='rgb',
                        help='Experimental full-image color neutralization for orange-ball footage')
    args = parser.parse_args()
    last = [-1, '']
    def progress(stage, done, total):
        if stage != last[1] or done - last[0] >= 25 or done == total:
            print(f'{stage}: {done}/{total}', file=sys.stderr, flush=True)
            last[:] = [done, stage]
    try:
        report = analyze(args.video, args.output, weights=args.weights, device=args.device,
                         threshold=args.threshold, max_frames=args.max_frames,
                         max_duration=args.max_duration, progress=progress, photometric=args.photometric)
    except Exception as exc:
        print(f'Analysis failed: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
