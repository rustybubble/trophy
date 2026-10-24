"""Trophy P0 spike: SpacetimeDB reducer-over-HTTP RTT and reducer->subscription latency.

stdlib only. Starts the TS subscriber (client/), waits for READY, calls a reducer N times
at ~RATE Hz with sent_ms = time.time()*1000, records HTTP round-trip time, then reads the
subscriber's SUMMARY line (Date.now() - sent_ms per inserted row).

  python bench.py --mode single  --n 200 --rate 20           # post_ping, new TCP conn per call (urllib)
  python bench.py --mode single  --n 200 --rate 20 --keepalive  # post_ping over one http.client conn
  python bench.py --mode batch   --n 20  --rate 20 --rows 10  # post_batch(batch_json) 10 rows/call
  python bench.py --mode typed   --n 20  --rate 20 --rows 10  # post_batch_typed(rows) 10 rows/call
  add --confirmed true|false to set the subscriber's withConfirmedReads()

Token: $STDB_TOKEN, else spacetimedb_token from the CLI config (cli.toml).
"""
import argparse, http.client, json, os, re, statistics, subprocess, sys, threading, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parent / "client"


def token() -> str:
    if os.environ.get("STDB_TOKEN"):
        return os.environ["STDB_TOKEN"]
    cfg = Path(os.environ.get("STDB_CLI_TOML", Path.home() / ".spacetimedb" / "config" / "cli.toml"))
    return re.search(r'spacetimedb_token = "([^"]+)"', cfg.read_text()).group(1)


def pct(xs, p):
    s = sorted(xs)
    return s[min(len(s) - 1, max(0, -(-p * len(s) // 100) - 1))]


def summarize(xs):
    return {"n": len(xs), "p50_ms": round(pct(xs, 50), 2), "p95_ms": round(pct(xs, 95), 2),
            "max_ms": round(max(xs), 2), "min_ms": round(min(xs), 2), "mean_ms": round(statistics.fmean(xs), 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["single", "batch", "typed"], default="single")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--rate", type=float, default=20.0)
    ap.add_argument("--rows", type=int, default=10)
    ap.add_argument("--keepalive", action="store_true")
    ap.add_argument("--host", default="127.0.0.1:3000")
    ap.add_argument("--db", default="trophy-spike")
    ap.add_argument("--out", default=None, help="subscriber per-row JSONL output")
    ap.add_argument("--confirmed", choices=["true", "false"], default=None, help="subscriber withConfirmedReads(); default: server default")
    a = ap.parse_args()

    tok = token()
    tag = f"{a.mode}{'-ka' if a.keepalive else ''}-{int(time.time())}"
    rows_per_call = 1 if a.mode == "single" else a.rows
    expect = a.n * rows_per_call

    cmd = ["npx", "tsx", "src/subscriber.ts", "--uri", f"ws://{a.host}", "--db", a.db,
           "--tag", tag, "--expect", str(expect)]
    if a.out:
        cmd += ["--out", str(Path(a.out).resolve())]
    if a.confirmed:
        cmd += ["--confirmed", a.confirmed]
    sub = subprocess.Popen(cmd, cwd=CLIENT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, encoding="utf-8", errors="replace", shell=(os.name == "nt"))
    lines, ready = [], threading.Event()

    def pump():
        for line in sub.stdout:
            lines.append(line.rstrip())
            if line.startswith("READY"):
                ready.set()
    threading.Thread(target=pump, daemon=True).start()
    if not ready.wait(30):
        sys.exit("subscriber not ready:\n" + "\n".join(lines))

    reducer = {"single": "post_ping", "batch": "post_batch", "typed": "post_batch_typed"}[a.mode]
    path = f"/v1/database/{a.db}/call/{reducer}"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {tok}"}
    conn = http.client.HTTPConnection(a.host) if a.keepalive else None

    rtts, errors, last_start = [], 0, 0.0
    period = 1.0 / a.rate
    t0 = time.perf_counter()
    for i in range(a.n):
        target = t0 + i * period
        while (d := target - time.perf_counter()) > 0:
            time.sleep(d)
        last_start = time.perf_counter()
        sent_ms = time.time() * 1000
        if a.mode == "single":
            body = [sent_ms, f"{tag}-{i}"]                                   # positional args array
        elif a.mode == "batch":
            batch = [{"sent_ms": sent_ms, "payload": f"{tag}-{i}-{j}"} for j in range(a.rows)]
            body = [json.dumps(batch)]                                       # ONE string arg, wrapped in an array
        else:
            body = [[{"sent_ms": sent_ms, "payload": f"{tag}-{i}-{j}"} for j in range(a.rows)]]
        data = json.dumps(body).encode()
        s = time.perf_counter()
        if conn:
            conn.request("POST", path, body=data, headers=headers)
            r = conn.getresponse(); r.read(); status = r.status
        else:
            req = urllib.request.Request(f"http://{a.host}{path}", data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req) as r:
                r.read(); status = r.status
        rtts.append((time.perf_counter() - s) * 1000)
        if status != 200:
            errors += 1
    span = last_start - t0  # first call start -> last call start

    try:
        sub.wait(30)
    except subprocess.TimeoutExpired:
        sub.kill()
    time.sleep(0.2)
    summ = next((json.loads(l[len("SUMMARY "):]) for l in lines if l.startswith("SUMMARY ")), None)
    result = {
        "mode": a.mode, "keepalive": a.keepalive, "confirmed_reads": a.confirmed or "server-default", "calls": a.n, "rows_per_call": rows_per_call,
        "target_rate_hz": a.rate, "achieved_rate_hz": round((a.n - 1) / span, 2) if span > 0 else None, "http_errors": errors,
        "http_rtt": summarize(rtts),
        "reducer_to_subscriber": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in summ.items()} if summ else None,
    }
    print(json.dumps(result))
    if not summ:
        print("\n".join(lines), file=sys.stderr)


if __name__ == "__main__":
    main()
