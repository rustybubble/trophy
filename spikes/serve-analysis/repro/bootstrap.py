"""Create four independent pinned runtimes; optionally restore the private kit."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import venv

from bundle import ROOT, import_bundle

ENVIRONMENTS = {'.venv': 'requirements.lock', '.venv-pose': 'requirements-pose.lock',
                '.venv-serves': 'requirements-serves.lock', '.venv-hmr2': 'requirements-hmr2.lock'}


def command(args):
    env = dict(os.environ, PYTHONNOUSERSITE='1')
    env.pop('PYTHONPATH', None)
    print('+', ' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=ROOT, env=env, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--uv', type=Path, help='Optional already installed uv executable')
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        raise SystemExit('Run with Python 3.12. Native macOS is the validated platform; POSIX CPU is supported but slower.')
    if args.bundle:
        import_bundle(args.bundle)
    if args.uv:
        uv = args.uv.resolve()
    else:
        tools = ROOT/'.venv-tools'
        if not (tools/'bin/python').exists():
            venv.EnvBuilder(with_pip=True).create(tools)
        command([tools/'bin/python', '-m', 'pip', 'install', 'uv==0.13.5'])
        uv = tools/'bin/uv'
    for directory, lock in ENVIRONMENTS.items():
        environment = ROOT/directory
        if not (environment/'bin/python').exists():
            venv.EnvBuilder(with_pip=True).create(environment)
        install = [uv, 'pip', 'sync', '--strict', '--python', environment/'bin/python', ROOT/lock]
        if sys.platform.startswith('linux'):
            # These locks came from macOS. Select CPU wheels explicitly so Linux
            # does not require an unpinned CUDA driver/runtime dependency set.
            install += ['--torch-backend', 'cpu']
        command(install)
        paths = list((environment/'lib').glob('python*/site-packages/*.pth'))
        for path in paths:
            for line in path.read_text().splitlines():
                if line.startswith('/') and not Path(line).resolve().is_relative_to(ROOT):
                    raise ValueError(f'Environment imports another checkout through {path}: {line}')
    command([ROOT/'.venv/bin/python', ROOT/'repro/reproduce.py', 'doctor'])


if __name__ == '__main__':
    main()
