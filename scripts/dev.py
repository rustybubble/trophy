"""(Re)start the whole dev stack from the Procfile with one command, on Windows, macOS or Linux.

    python scripts/dev.py              # make dev / npm run dev
    python scripts/dev.py gateway pwa  # only these Procfile entries
    python3 scripts/dev.py --stop       # stop what a previous run started, and free the stack's ports

Restart semantics: first stops what the last run started (data/local/dev.pids), anything still listening on the
stack's ports, any leftover `python -m flight`, and the `trophy-redis` container (Redis has no persistence). Then
starts each entry in Procfile order, after the ports it depends on (WAITS) accept connections. Output lines are
prefixed with the entry's name. If one entry exits, the others keep running; Ctrl-C stops them all.
$VARS in the Procfile come from the environment, then .env, then DEFAULTS.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import shlex
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIDS = ROOT / "data" / "local" / "dev.pids"
# $PYTHON: the interpreter running this script, quoted for the shell (Windows paths often contain spaces)
PY = f'"{sys.executable}"' if os.name == "nt" else shlex.quote(sys.executable)
DEFAULTS = {"SPACETIME": "spacetime", "PYTHON": PY}
PORTS = {
    "redis": 6379,
    "spacetime": 3000,
    "gateway": 8000,
    "referee": 8100,
    "voice": 8765,
    "pwa": 5173,
    "dashboard": 5174,
    "watch": 5175,
    "caddy": 443,
}
WAITS = {
    "gateway": [6379, 3000],
    "recorder": [6379, 3000],
    "engine": [6379, 3000],
    "referee": [6379],
    "announcer": [6379],
    "compiler": [3000],
    "caddy": [8000, 5173, 5174, 5175],
    "flight": [6379, 3000, 8000],
    "live": [6379, 3000],
}
WIN = os.name == "nt"
COLOURS = [31, 32, 33, 34, 35, 36, 91, 92, 93, 94, 95, 96]


def env_file() -> dict[str, str]:
    out = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text("utf8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.split("#")[0].strip()
    return out


def procfile() -> list[tuple[str, str]]:
    env = {**DEFAULTS, **env_file(), **os.environ}
    out = []
    for line in (ROOT / "Procfile").read_text("utf8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, cmd = line.split(":", 1)
        out.append((name.strip(), re.sub(r"\$(\w+)", lambda m: env.get(m.group(1), m.group(0)), cmd.strip())))
    return out


def listening(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def kill_tree(pid: int) -> None:
    if WIN:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pid, signal.SIGTERM)


OURS = ("caddy", "python", "node", "uv", "spacetime", "redis-server")  # only these may be stopped for a stack port


def image_name(pid: int) -> str:
    if WIN:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True
        ).stdout
        return out.split(",")[0].strip('"').lower() if out.startswith('"') else ""
    # macOS reports the full executable path in `comm`; only the basename is compared against OURS
    comm = subprocess.run(["ps", "-p", str(pid), "-o", "comm="], capture_output=True, text=True).stdout.strip()
    return os.path.basename(comm).lower()


def port_pids(port: int) -> set[int]:
    if WIN:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True).stdout
        return {
            int(parts[-1])
            for parts in (line.split() for line in out.splitlines())
            if len(parts) >= 5 and parts[3] == "LISTENING" and parts[1].rsplit(":", 1)[-1] == str(port)
        }
    out = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"], capture_output=True, text=True).stdout
    return {int(p) for p in out.split()}


def stop_all(names: set[str]) -> None:
    if PIDS.exists():
        keep = []
        for line in PIDS.read_text().splitlines():
            name, pid = line.split()
            if name in names:
                kill_tree(int(pid))
            else:
                keep.append(line)
        PIDS.write_text("".join(f"{line}\n" for line in keep))
    for name, port in PORTS.items():
        if name in names:
            for pid in port_pids(port):
                img = image_name(pid)
                if any(img.startswith(o) for o in OURS):
                    print(f"dev: stopping {img} (pid {pid}) on port {port} ({name})")
                    kill_tree(pid)
                elif img:
                    print(f"dev: port {port} ({name}) is held by {img} (pid {pid}); not ours, left running")
    if "flight" in names:  # no port: find a leftover `python -m flight...` by its command line
        if WIN:
            ps = (
                "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*-m flight*' -and "
                "$_.Name -like 'python*' } | ForEach-Object { $_.ProcessId }"
            )
            out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout
            for pid in out.split():
                kill_tree(int(pid))
        else:
            subprocess.run(["pkill", "-f", "[ ]-m flight"], capture_output=True)
    if "redis" in names:  # the Windows setup's Docker container; brew's redis-server is caught by its port above
        with contextlib.suppress(FileNotFoundError):
            subprocess.run(["docker", "rm", "-f", "trophy-redis"], capture_output=True)


def pump(name: str, colour: int, proc: subprocess.Popen) -> None:
    assert proc.stdout
    for raw in proc.stdout:
        line = raw.decode("utf8", "replace").rstrip()
        print(f"\x1b[{colour}m{name:>9} |\x1b[0m {line}", flush=True)
    print(f"\x1b[{colour}m{name:>9} |\x1b[0m exited with code {proc.wait()}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("only", nargs="*", help="Procfile entries to (re)start (default: all)")
    ap.add_argument("--stop", action="store_true")
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):  # a Windows console is cp1252: never let a child's output kill a pump
        stream.reconfigure(errors="replace")  # type: ignore[attr-defined]
    entries = [(n, c) for n, c in procfile() if not a.only or n in a.only]
    stop_all({n for n, _ in entries})
    if a.stop:
        return 0
    PIDS.parent.mkdir(parents=True, exist_ok=True)
    procs: list[tuple[str, subprocess.Popen]] = []
    for i, (name, cmd) in enumerate(entries):
        for port in WAITS.get(name, []):
            t0 = time.time()
            while not listening(port) and time.time() - t0 < 60:
                time.sleep(0.5)
            if not listening(port):
                print(f"dev: {name}: port {port} still closed after 60 s; starting anyway")
        # Windows: through cmd.exe (npm is a .cmd); POSIX: own session so the whole tree can be stopped
        kw: dict = (
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP, "shell": True}
            if WIN
            else {"start_new_session": True}
        )
        proc = subprocess.Popen(
            cmd if WIN else shlex.split(cmd),
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env={**env_file(), **os.environ, "PYTHONUNBUFFERED": "1"},  # .env reaches every entry; the shell wins
            **kw,
        )
        procs.append((name, proc))
        with PIDS.open("a") as f:
            f.write(f"{name} {proc.pid}\n")
        threading.Thread(target=pump, args=(name, COLOURS[i % len(COLOURS)], proc), daemon=True).start()
        print(f"dev: started {name} (pid {proc.pid})", flush=True)
    try:
        while any(p.poll() is None for _, p in procs):
            time.sleep(1)
    except KeyboardInterrupt:
        print("dev: stopping", flush=True)
        stop_all({n for n, _ in entries})
    return 0


if __name__ == "__main__":
    sys.exit(main())
