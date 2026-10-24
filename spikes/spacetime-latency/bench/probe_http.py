"""Probe SpacetimeDB HTTP reducer-call formats and auth (stdlib only). Prints (status, body) per case.
Token: spacetimedb_token from ~/.spacetimedb/config/cli.toml (the publisher identity).
"""
import json, sys, time, urllib.request, urllib.error, re, os
BASE = "http://127.0.0.1:3000"; DB = "trophy-spike"
def call(reducer, body, token=None, raw=False):
    data = body if raw else json.dumps(body).encode()
    h = {"Content-Type": "application/json"}
    if token: h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}/v1/database/{DB}/call/{reducer}", data=data, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req) as r: return r.status, r.read().decode()[:300]
    except urllib.error.HTTPError as e: return e.code, e.read().decode()[:300]
toml = open(os.path.join(os.path.expanduser("~"), ".spacetimedb", "config", "cli.toml")).read()
cli_tok = re.search(r'spacetimedb_token = "([^"]+)"', toml).group(1)
new = json.loads(urllib.request.urlopen(urllib.request.Request(BASE+"/v1/identity", method="POST")).read())
now = time.time()*1000
tests = [
 ("post_ping array", "post_ping", [now, "a"], cli_tok),
 ("post_ping object", "post_ping", {"sent_ms": now, "payload": "o"}, cli_tok),
 ("post_ping no auth", "post_ping", [now, "noauth"], None),
 ("post_ping int sent_ms", "post_ping", [int(now), "int"], cli_tok),
 ("post_batch", "post_batch", [json.dumps([{"sent_ms": now, "payload": "b1"}, {"sent_ms": now, "payload": "b2"}])], cli_tok),
 ("post_batch bare string (not array)", "post_batch", json.dumps([{"sent_ms": now, "payload": "bx"}]), cli_tok),
 ("post_batch bad json", "post_batch", ["not json"], cli_tok),
 ("post_batch_typed array-of-arrays", "post_batch_typed", [[[now, "t1"], [now, "t2"]]], cli_tok),
 ("post_batch_typed array-of-objects", "post_batch_typed", [[{"sent_ms": now, "payload": "t3"}]], cli_tok),
 ("guarded_ping publisher", "guarded_ping", [now, "g-ok"], cli_tok),
 ("guarded_ping other identity", "guarded_ping", [now, "g-bad"], new["token"]),
 ("guarded_ping no auth", "guarded_ping", [now, "g-anon"], None),
 ("camelCase name", "postPing", [now, "cc"], cli_tok),
]
for name, red, body, tok in tests:
    print(f"{name:40s}", call(red, body, tok))
print("other identity:", new["identity"])
