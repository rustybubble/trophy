"""Point trophy.photo's A record at this Mac's current LAN IP (Porkbun DNS API), for when the demo network changes.

    python3 infra/caddy/point_dns.py            # show the current record and this Mac's IP, change nothing
    python3 infra/caddy/point_dns.py --apply    # set the apex A record to this Mac's IP (TTL 600)

Reads PORKBUN_API_KEY / PORKBUN_SECRET_API_KEY (and TROPHY_DOMAIN) from .env. Phones must be on a network where
devices can reach each other (venue Wi-Fi often isolates clients; an iPhone Personal Hotspot does not).
The certificate is unaffected: Caddy proves the domain with DNS-01, not by IP.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = "https://api.porkbun.com/api/json/v3"


def env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / ".env").read_text("utf8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.split(" #")[0].strip()
    return out


def lan_ip() -> str:
    iface = subprocess.run(["route", "-n", "get", "default"], capture_output=True, text=True).stdout
    dev = next((ln.split(":")[1].strip() for ln in iface.splitlines() if "interface:" in ln), "en0")
    ip = subprocess.run(["ipconfig", "getifaddr", dev], capture_output=True, text=True).stdout.strip()
    if not ip:
        sys.exit(f"no IPv4 address on {dev}")
    return ip


def call(path: str, body: dict) -> dict:
    req = urllib.request.Request(f"{API}/{path}", data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="change the record (default: only show it)")
    a = ap.parse_args()
    e = env()
    domain = e.get("TROPHY_DOMAIN") or "trophy.photo"
    auth = {"apikey": e["PORKBUN_API_KEY"], "secretapikey": e["PORKBUN_SECRET_API_KEY"]}
    ip = lan_ip()
    cur = call(f"dns/retrieveByNameType/{domain}/A", auth).get("records") or []
    now = [r["content"] for r in cur]
    print(f"{domain} A -> {', '.join(now) or '(none)'}; this Mac -> {ip}")
    if not a.apply:
        return 0
    if now == [ip]:
        print("already pointing here")
        return 0
    res = call(f"dns/editByNameType/{domain}/A", {**auth, "content": ip, "ttl": "600"})
    print("updated" if res.get("status") == "SUCCESS" else f"failed: {res}")
    return 0 if res.get("status") == "SUCCESS" else 1


if __name__ == "__main__":
    sys.exit(main())
