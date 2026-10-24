"""Point $TROPHY_DOMAIN at this machine's LAN IP through the Porkbun DNS API (infra/README.md).

    python infra/dns/porkbun_set_ip.py            # detect the LAN IP and update the apex A record
    python infra/dns/porkbun_set_ip.py 10.0.0.5   # explicit IP
    python infra/dns/porkbun_set_ip.py --show     # list records only

Rerun whenever DHCP gives the demo machine a new address. An existing apex A or ALIAS record (Porkbun's parking
default) is edited in place; nothing is deleted. Reads PORKBUN_API_KEY / PORKBUN_SECRET_API_KEY from .env and
never prints them.
"""

from __future__ import annotations

import json
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = "https://api.porkbun.com/api/json/v3/"
TTL = "600"  # Porkbun's minimum


def env() -> dict[str, str]:
    out = {}
    for line in (ROOT / ".env").read_text("utf8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.split("#")[0].strip()
    return out


ENV = env()
DOMAIN = ENV.get("TROPHY_DOMAIN", "trophy.photo")


def call(path: str, **body: str) -> dict:
    data = {"apikey": ENV["PORKBUN_API_KEY"], "secretapikey": ENV["PORKBUN_SECRET_API_KEY"], **body}
    req = urllib.request.Request(
        API + path, data=json.dumps(data).encode(), method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"porkbun {path}: HTTP {e.code}: {e.read().decode()[:200]}") from None


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 53))  # no packet is sent; this just picks the outbound interface
        return s.getsockname()[0]
    finally:
        s.close()


def main() -> None:
    records = call(f"dns/retrieve/{DOMAIN}")["records"]
    if "--show" in sys.argv:
        for r in records:
            print(r["id"], r["type"], r["name"], r["content"], r["ttl"])
        return
    ip = next((a for a in sys.argv[1:] if not a.startswith("-")), None) or lan_ip()
    apex = [r for r in records if r["name"] == DOMAIN and r["type"] in ("A", "ALIAS", "CNAME")]
    if apex:
        r = apex[0]
        if r["type"] == "A" and r["content"] == ip:
            print(f"{DOMAIN} A {ip} already set")
            return
        call(f"dns/edit/{DOMAIN}/{r['id']}", type="A", name="", content=ip, ttl=TTL)
        print(f"{DOMAIN}: {r['type']} {r['content']} -> A {ip} (record {r['id']} edited)")
    else:
        rid = call(f"dns/create/{DOMAIN}", type="A", name="", content=ip, ttl=TTL)["id"]
        print(f"{DOMAIN}: created A {ip} (record {rid})")


if __name__ == "__main__":
    main()
