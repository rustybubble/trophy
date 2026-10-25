#!/usr/bin/env python3
"""Trophy's PreToolUse hook: the file and command allowlist, enforced by the CLI before a tool runs.

Autonomy "low" auto-approves file edits without asking the SDK's permission handler, and "off" offers no edit tools
at all, so this hook is where the sandbox's scoping actually happens (measured 2026-10-24, droid 0.249 / SDK 0.10).
It reads the hook payload on stdin ({tool_name, tool_input, cwd, ...}), reads the allowlist written by the runner
(.trophy/allowlist.json, read-only), and exits 2 with the reason on stderr to block the call. Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import sys

EDIT_TOOLS = {"Edit", "Create", "ApplyPatch", "MultiEdit", "Write"}
EXEC_TOOLS = {"Execute"}
# the job's gate, bare or with --quiet; single literal spaces only (see allowlist.ts). fullmatch: no trailing newline
TEST_CMD = re.compile(r"(\./)?(replay_test|check_test)( --quiet)?")
PRINTABLE = re.compile(r"[\x20-\x7e]*")
DEFAULT_COMMANDS = ["./replay_test"]  # sandboxes written before `commands` existed in allowlist.json
SHELL_META = ("&&", "||", ";", "|", "`", "$", "<", ">")


def block(msg: str) -> None:
    sys.stderr.write(f"trophy sandbox: {msg}\n")
    sys.exit(2)


def norm(p: str) -> str:
    return os.path.realpath(p)


def allowed_command(cmd: str, sandbox: str, commands: list[str]) -> bool:
    """The job's gate script (`./replay_test` or `./check_test`, per `commands`), optionally with flags."""
    if not PRINTABLE.fullmatch(cmd):
        return False  # a newline or other control character could smuggle a second command
    c = cmd.strip()
    d = sandbox.rstrip("/")
    for q in ('"', "'", ""):
        prefix = f"cd {q}{d}{q} && "
        if c.startswith(prefix):
            c = c[len(prefix) :]
            break
        real = norm(d)
        prefix = f"cd {q}{real}{q} && "
        if c.startswith(prefix):
            c = c[len(prefix) :]
            break
    if any(m in c for m in SHELL_META):
        return False
    m = TEST_CMD.fullmatch(c)
    return bool(m) and m.group(2) in {str(x).removeprefix("./") for x in commands}


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        block("unreadable hook payload")
        return
    sandbox = sys.argv[1] if len(sys.argv) > 1 else payload.get("cwd") or os.getcwd()
    try:
        with open(os.path.join(sandbox, ".trophy", "allowlist.json"), encoding="utf8") as f:
            allow = json.load(f)
    except OSError:
        block("allowlist missing; refusing every write")
        return
    allowed_files = {norm(os.path.join(sandbox, rel)) for rel in allow.get("files", [])}
    tool = str(payload.get("tool_name") or payload.get("toolName") or "")
    inp = payload.get("tool_input") or payload.get("toolInput") or {}
    if tool in EDIT_TOOLS:
        paths = []
        for k in ("file_path", "filePath", "path", "target_file"):
            if isinstance(inp.get(k), str):
                paths.append(inp[k])
        for f in inp.get("files") or []:  # ApplyPatch-style multi-file inputs
            if isinstance(f, dict):
                for k in ("path", "file_path"):
                    if isinstance(f.get(k), str):
                        paths.append(f[k])
        if not paths:
            block(f"{tool}: no file path in the tool input")
        for p in paths:
            ab = norm(p if os.path.isabs(p) else os.path.join(sandbox, p))
            if ab not in allowed_files:
                block(f"{tool} refused: {p} is not in the allowlist {sorted(allow.get('files', []))}")
        return
    if tool in EXEC_TOOLS:
        cmd = str(inp.get("command") or inp.get("fullCommand") or "")
        commands = list(allow.get("commands") or DEFAULT_COMMANDS)
        if not allowed_command(cmd, sandbox, commands):
            block(f"command refused: only {' or '.join(commands)} may run (got: {cmd[:120]!r})")
        return
    # read-only tools pass


if __name__ == "__main__":
    main()
