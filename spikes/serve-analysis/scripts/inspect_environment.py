"""Record native execution and available local tools without hardware identifiers."""
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import torch
import imageio_ffmpeg


def command(args):
    r = subprocess.run(args, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else {'unavailable': r.stderr.strip()}

info = dict(os=platform.platform(), architecture=platform.machine(), python=sys.version,
            executable=sys.executable, system_python=shutil.which('python3'),
            system_uv=shutil.which('uv'), system_ffmpeg=shutil.which('ffmpeg'),
            system_ffprobe=shutil.which('ffprobe'),
            memory_bytes=command(['sysctl', '-n', 'hw.memsize']),
            cpu=command(['sysctl', '-n', 'machdep.cpu.brand_string']),
            disk_free_bytes=shutil.disk_usage('.').free,
            uv=command(['.venv/bin/uv', '--version']),
            torch=torch.__version__, mps_built=torch.backends.mps.is_built(),
            mps_available=torch.backends.mps.is_available(),
            ffmpeg_binary=imageio_ffmpeg.get_ffmpeg_exe(),
            ffmpeg_version=imageio_ffmpeg.get_ffmpeg_version())
print(json.dumps(info, indent=2))
