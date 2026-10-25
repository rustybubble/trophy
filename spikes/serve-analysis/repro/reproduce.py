"""Reproduce the recorded analysis from the checkout plus verified private assets."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from bundle import ROOT, REPO, MANIFEST, verify

PROFILES = Path(__file__).with_name('profiles')


def run_command(args):
    env = dict(os.environ, PYTHONNOUSERSITE='1')
    env.pop('PYTHONPATH', None)
    print('+', ' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=ROOT, env=env, check=True)


def doctor():
    failures = []
    try:
        node = subprocess.check_output([os.environ.get('TROPHY_NODE', 'node'), '--version'], text=True).strip()
        if int(node.lstrip('v').split('.')[0]) < 20:
            raise ValueError('Node.js 20 or newer is required')
        print(f'Node.js: {node}', flush=True)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        failures.append(f'Node.js: {exc}; install Node >=20 or set TROPHY_NODE to its executable')
    assets = verify(groups=['runtime', 'recordings', 'samples'])
    failures.extend('Missing asset: '+p for p in assets['missing'])
    failures.extend('Asset checksum mismatch: '+p for p in assets['mismatched'])
    imports = {
        '.venv': 'import torch,numpy,cv2,av,scipy,streamlit,pyarrow',
        '.venv-pose': 'import mediapipe,numpy,cv2',
        '.venv-serves': 'import torch,torchvision,timm,numpy,av,cv2',
        '.venv-hmr2': 'import torch,torchvision,timm,smplx,skimage,scipy,pyrender; from trophy.replay.hmr2 import official_imports; official_imports()',
    }
    for name, code in imports.items():
        try:
            run_command([ROOT/name/'bin/python', '-c', code+'; import sys; print(sys.executable)'])
        except (OSError, subprocess.CalledProcessError) as exc:
            failures.append(f'{name}: {exc}')
    for item in json.loads(MANIFEST.read_text())['files']:
        if item['group'] in ['runtime', 'recordings'] and not (REPO/item['path']).is_file():
            failures.append('Missing asset: '+item['path'])
    print(json.dumps(dict(ready=not failures, errors=failures), indent=2))
    if failures:
        raise SystemExit(1)


def materialize(profile, output):
    data = json.loads((PROFILES/(profile+'.json')).read_text())
    config = data['config']
    for view in config['views']:
        path = (ROOT/view['video']).resolve()
        if not path.is_file():
            raise FileNotFoundError(f'Import the private kit first: {path}')
        view['video'] = str(path)
    path = output/'input-config.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2))
    return path, data


def ball_excerpt(output):
    import imageio_ffmpeg
    run_command([imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error',
                 '-ss', '4.4', '-i', output/'ball-only-3d.mp4', '-t', '10.6', '-an',
                 '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18',
                 '-movflags', '+faststart', output/'rally-3d.mp4'])
    run_command([ROOT/'.venv/bin/python', '-c',
                 'from trophy.pipeline import verify_video; import sys; print(verify_video(sys.argv[1],318,30))',
                 output/'rally-3d.mp4'])


def verify_result(output, expected=None):
    import numpy as np
    output = Path(output)
    scene = json.loads((output/'replay/scene.json').read_text())
    report = json.loads((output/'session-report.json').read_text())
    geometry = json.loads((output/'hmr2/geometry.json').read_text())
    assert report['status'] == 'complete'
    vertices = np.fromfile(output/'replay/vertices.f32', dtype='<f4')
    faces = np.fromfile(output/'replay/faces.u32', dtype='<u4')
    assert vertices.size == scene['frame_count']*scene['players']*scene['vertex_count']*3
    assert np.isfinite(vertices).all() and faces.size and faces.max() < scene['vertex_count']
    assert all(frame['ball'] == geometry['ball'][frame['frame_index']] for frame in scene['frames'])
    assert report['synchronization']['residual_clip_offset_seconds'] == scene['source_offsets_seconds'][1]
    review = json.loads((output/'replay/review/serves.json').read_text())
    assert review['views'][1]['source_offset_seconds'] == scene['source_offsets_seconds'][1]
    assert scene['report']['reprojection_after']['median_px'] < scene['report']['reprojection_before']['median_px']
    result = dict(verified=True, frames=scene['frame_count'], ball_frames=geometry['ball_report']['valid_frames'],
                  body_median_reprojection_px=scene['report']['reprojection_after']['median_px'],
                  original_offset_seconds=report['synchronization']['original_offset_seconds'],
                  start_time=scene['start_time'], end_time=scene['duration'])
    if expected:
        assert abs(result['frames']-expected['frames']) <= expected.get('frame_tolerance', 5)
        assert abs(result['ball_frames']-expected['ball_frames']) <= expected.get('ball_frame_tolerance', 20)
        assert result['body_median_reprojection_px'] < expected['max_body_median_reprojection_px']
        assert abs(result['original_offset_seconds']-expected['original_offset_seconds']) < .03
        result['reference_tolerances_passed'] = True
    print(json.dumps(result, indent=2), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    actions.add_parser('doctor')
    runner = actions.add_parser('run')
    runner.add_argument('profile', choices=['room-demo-15s', 'public-smoke', 'serves-original', 'toss-original', 'legacy-hmr2', 'ball-only'])
    runner.add_argument('--output', type=Path)
    runner.add_argument('--device', choices=['auto', 'cpu', 'mps'], default='auto')
    checker = actions.add_parser('check-result')
    checker.add_argument('output', type=Path)
    checker.add_argument('--profile', choices=['room-demo-15s', 'public-smoke'])
    server = actions.add_parser('serve')
    server.add_argument('--directory', type=Path, default=ROOT/'artifacts/sessions/ccc43c2099f540f2/replay')
    server.add_argument('--port', type=int, default=8508)
    actions.add_parser('test')
    args = parser.parse_args()
    if args.action == 'doctor':
        doctor()
    elif args.action == 'test':
        run_command([ROOT/'.venv/bin/python', '-m', 'pytest', '-q'])
        run_command([os.environ.get('TROPHY_NODE', 'node'), '--test', *sorted((ROOT/'tests').glob('*.mjs'))])
    elif args.action == 'serve':
        run_command([ROOT/'.venv/bin/python', ROOT/'scripts/serve_replay.py', '--directory', args.directory.resolve(), '--port', args.port])
    elif args.action == 'check-result':
        expected = json.loads((PROFILES/(args.profile+'.json')).read_text())['expected'] if args.profile else None
        verify_result(args.output.resolve(), expected)
    else:
        output = args.output.resolve() if args.output else ROOT/'artifacts/reproductions'/f'{args.profile}-{time.time_ns()}'
        if output.exists():
            raise ValueError('Choose a new output directory; reference artifacts are never overwritten')
        if args.profile in ['room-demo-15s', 'public-smoke', 'serves-original']:
            config_path, profile = materialize(args.profile, output)
            if args.profile == 'serves-original':
                run_command([ROOT/'.venv-serves/bin/python', ROOT/'scripts/detect_serves.py', '--config', config_path,
                             '--output', output/'serves', '--device', args.device, '--max-seconds', 120])
            else:
                config = json.loads(config_path.read_text()); config['device'] = args.device
                config_path.write_text(json.dumps(config, indent=2))
                run_command([ROOT/'.venv/bin/python', ROOT/'scripts/analyze_two_camera.py', '--config', config_path,
                             '--output', output/'analysis'])
                verify_result(output/'analysis', profile['expected'])
        elif args.profile == 'toss-original':
            config_path, _ = materialize('serves-original', output)
            run_command([ROOT/'.venv-serves/bin/python', ROOT/'scripts/build_actual_toss_demo.py', '--session', config_path,
                         '--geometry', ROOT/'configs/actual-toss-demo-geometry.json', '--output', output/'demo'])
        elif args.profile == 'ball-only':
            run_command([ROOT/'.venv/bin/python', ROOT/'scripts/build_ball_only_replay.py',
                         '--session', ROOT/'artifacts/sessions/ccc43c2099f540f2',
                         '--config', PROFILES/'ball-only-inspected.json', '--output', output])
            run_command([ROOT/'.venv-hmr2/bin/python', ROOT/'scripts/render_ball_only_replay.py',
                         '--directory', output])
            ball_excerpt(output)
        elif args.profile == 'legacy-hmr2':
            inputs = output/'hmr2'; inputs.mkdir(parents=True)
            original = ROOT/'artifacts/user-two-camera/hmr2'
            for name in ['geometry.json', 'geometry.npz', 'poses-camera1.json', 'poses-camera2.json']:
                shutil.copy2(original/name, inputs/name)
            selected = args.device
            if selected == 'auto':
                import torch
                selected = 'mps' if torch.backends.mps.is_available() else 'cpu'
            for view in [1, 2]:
                run_command([ROOT/'.venv-hmr2/bin/python', ROOT/'scripts/run_hmr2.py',
                    '--video', ROOT/f'artifacts/user-two-camera/camera{view}-8s-14s.mp4',
                    '--poses', inputs/f'poses-camera{view}.json', '--output', inputs/f'inference-camera{view}',
                    '--device', selected, '--stride', 2, '--max-frames', 180])
            run_command([ROOT/'.venv-hmr2/bin/python', ROOT/'scripts/fit_hmr2_multiview.py', '--inputs', inputs,
                         '--output', output/'replay', '--device', selected])
            run_command([ROOT/'.venv-hmr2/bin/python', ROOT/'scripts/render_hmr2_replay.py', '--directory', output/'replay'])
        print(f'Reproduction output: {output}', flush=True)


if __name__ == '__main__':
    main()
