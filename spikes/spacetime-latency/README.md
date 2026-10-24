# Spike: SpacetimeDB reducer (HTTP) → TS subscription latency

P0 spike, 2026-10-24. **All numbers below were measured on Windows 11 localhost**, not on the M5 Pro Mac
that the plan assumes. Treat them as an indication of order of magnitude for the Mac, not a Mac measurement.

- Machine: Windows 11 Home (build 26200), Intel Core Ultra 5 125U, 15.4 GB RAM, on battery/AC not controlled.
- SpacetimeDB CLI + standalone server **2.13.0** (commit `08e1aba133671f9c631c6e70133a82faa0e7b283`).
- npm `spacetimedb@2.13.0` (module and client), Node 22.16.0, Python 3.11.9 (stdlib only).
- Local server only (`spacetime start`). No spacetimedb.com / maincloud account or login was used.

## Results (measured, Windows 11, everything on 127.0.0.1)

Method: `bench/bench.py` starts the TS subscriber (`client/`), waits until its subscription to
`SELECT * FROM ping` is applied, then calls a reducer over HTTP at 20 Hz (scheduled against
`perf_counter`, achieved 19.96–20.0 Hz). Each call carries `sent_ms = time.time()*1000`, taken just
before the request is built. **HTTP RTT** is `perf_counter` around the `urlopen` (or `http.client`)
call, including reading the response. **Reducer→subscriber** is `Date.now() - row.sentMs` in the
subscriber's `onInsert` callback (same host, same clock; Node `Date.now()` has 1 ms resolution, so
treat values as ±1 ms). Rows present before the subscription was applied are ignored. Single runs, no
warm-up discarded; raw summaries are in `results/windows11-localhost-2026-10-24.jsonl`.

| Run | Calls × rows | HTTP RTT p50 / p95 / max (ms) | Reducer→subscriber p50 / p95 / max (ms) |
|---|---|---|---|
| `post_ping`, urllib (new TCP conn per call), run A | 200 × 1 | 4.41 / 7.06 / 21.43 | 3.44 / 6.15 / 21.12 |
| `post_ping`, urllib, run B | 200 × 1 | 5.93 / 8.05 / 10.80 | 4.96 / 7.61 / 10.45 |
| `post_ping`, `http.client` keep-alive | 200 × 1 | 4.55 / 5.73 / 9.34 | 3.36 / 5.08 / 10.39 |
| `post_batch` (one JSON string arg), urllib | 200 × 10 | 6.92 / 8.06 / 72.31 | 6.45 / 8.04 / 72.34 (n=2000 rows) |
| `post_batch_typed` (`t.array(PingIn)`), urllib | 200 × 10 | 7.47 / 9.24 / 17.57 | 6.54 / 8.52 / 17.25 (n=2000 rows) |
| `post_ping`, subscriber `withConfirmedReads(true)` | 200 × 1 | 5.90 / 7.25 / 12.10 | 5.25 / 6.53 / 11.84 |
| `post_ping`, subscriber `withConfirmedReads(false)` | 200 × 1 | 6.25 / 8.47 / 16.11 | 2.42 / 3.85 / 14.57 |

(Short 20-call batch runs gave similar values: `post_batch` RTT p50 5.01 ms, delivery p50 5.72 ms;
`post_batch_typed` RTT p50 3.88 ms, delivery p50 4.76 ms.)

Observations (measured, single runs, so small differences are within noise):
- The subscription update reaches the subscriber **before** the HTTP response returns to the caller
  (delivery p50 ≈ 1 ms below RTT p50).
- End-to-end delivery is single-digit ms at p95 for single rows and for 10-row batches; occasional
  spikes reached 21 ms and 72 ms (one each, not investigated).
- JSON-string batch and typed-array batch performed about the same.
- Turning confirmed reads off on the subscriber roughly halved delivery p50 (2.4 vs 5.3 ms). The
  server default behaved like something between the two in these runs; we did not determine it.

## Install (what was run)

Official Windows installer, per https://spacetimedb.com/install:

```powershell
iwr https://windows.spacetimedb.com -useb | iex
```

That script checks for `vcruntime140.dll`, downloads
`https://github.com/clockworklabs/SpacetimeDB/releases/latest/download/spacetimedb-update-x86_64-pc-windows-msvc.exe`,
runs it (interactive `self-install`), and appends `%LOCALAPPDATA%\SpacetimeDB` to the user `Path`.
Latest release on 2026-10-24 was `v2.13.0` (2026-10-21).

What was actually run (same binary, pinned to the v2.13.0 tag, non-interactive):

```bash
curl -sSL -o spacetimedb-update.exe \
  https://github.com/clockworklabs/SpacetimeDB/releases/download/v2.13.0/spacetimedb-update-x86_64-pc-windows-msvc.exe
./spacetimedb-update.exe self-install --root-dir 'C:\Users\Joseph\.spacetimedb' --yes
```

Why `--root-dir`: this agent runs inside the Claude desktop app, which is an MSIX package, so writes
to `%LOCALAPPDATA%` were redirected to the package's private cache. The default install's
`bin\current` junction then pointed at a path that didn't exist, and `spacetime` failed with "the
spacetime version set as current may not exist". That is an artifact of the agent sandbox, not of
SpacetimeDB; a normal terminal install should be fine. On the Mac use
`curl -sSf https://install.spacetimedb.com | sh`.

With `--root-dir`, every command needs the root dir, **written with `=`**: `spacetime --root-dir X start`
(space-separated) failed with "a value is required for '--root-dir'"; `--root-dir=X` works.
Below, `spacetime` means `C:\Users\Joseph\.spacetimedb\spacetime.exe --root-dir=C:\Users\Joseph\.spacetimedb`.

```
$ spacetime --version
spacetimedb tool version 2.13.0; spacetimedb-lib version 2.13.0;
```

## Start / publish / generate

```bash
# server: plain HTTP + WS, no TLS
spacetime start --listen-addr 127.0.0.1:3000 --non-interactive     # default listen is 0.0.0.0:3000

# a fresh cli.toml defaults to maincloud: make local the default and always pass -s local
spacetime server set-default local

# from spikes/spacetime-latency/
(cd module && npm install)                                          # spacetimedb@2.13.0, typescript ~5.6
spacetime publish -s local -p module --yes=skip-login trophy-spike
#   "We have logged in directly to your target server. WARNING: This login will NOT work for any other servers."
#   "Logged in with identity c200822a..."   -> token saved as spacetimedb_token in config/cli.toml
#   "Created new database with name: trophy-spike, identity: c2004871..."
# republish after changes: same command (add --delete-data=on-conflict for breaking schema changes)

spacetime generate --lang typescript -p module -o client/src/module_bindings --no-config -y

spacetime sql trophy-spike "SELECT * FROM ping"
spacetime logs trophy-spike

# bench (needs the server running and the module published)
(cd client && npm install)
python -I bench/bench.py --mode single --n 200 --rate 20
python -I bench/bench.py --mode single --n 200 --rate 20 --keepalive
python -I bench/bench.py --mode batch  --n 200 --rate 20 --rows 10
python -I bench/bench.py --mode typed  --n 200 --rate 20 --rows 10
python -I bench/probe_http.py          # prints status/body for each HTTP body/auth variant below
```

No login to spacetimedb.com was needed: `--yes=skip-login` made the CLI fetch an identity + token
directly from the local server. `spacetime init --lang typescript --local` (used only to read the
template) still wrote `"server": "maincloud"` into `spacetime.json`; this spike has no `spacetime.json`
and passes `-s local` explicitly.

`node_modules/` is gitignored. The spike was developed with installs in a scratch directory; the
committed tree holds sources, lockfiles and generated bindings only.

## HTTP reducer call (verified)

```
POST http://127.0.0.1:3000/v1/database/{db-name-or-identity}/call/{reducer}
Content-Type: application/json
Authorization: Bearer <token>
<body: the reducer's arguments as JSON>
```

Body formats that returned **200**:

| Reducer | Body |
|---|---|
| `post_ping(sent_ms: f64, payload: string)` | `[1792865860843.49, "a"]` (positional array) |
| same | `{"sent_ms": 1792865860843.49, "payload": "o"}` (object keyed by **declared** arg names) |
| same | `[1792865860843, "int"]` (an integer is accepted for f64) |
| `post_batch(batch_json: string)` | `["[{\"sent_ms\": 1.0, \"payload\": \"b1\"}, ...]"]`, i.e. **the JSON text as a string inside a one-element array** (or `{"batch_json": "..."}`) |
| `post_batch_typed(rows: PingIn[])` | `[[{"sent_ms": 1.0, "payload": "t3"}]]` or `[[[1.0, "t1"], [1.0, "t2"]]]` |

In Python: `json.dumps([json.dumps(batch)])`.

Errors:

| Case | Status | Body |
|---|---|---|
| `post_batch` with a bare JSON string body (`"[{...}]"`, not wrapped in an array) | 400 | `invalid arguments for reducer post_batch: ... expected a post_batch tuple` |
| Reducer throws `SenderError` (bad JSON in `post_batch`, unauthorized sender) | **530** | the error message, e.g. `bad JSON: SyntaxError: ...` |
| Unknown reducer name (`postPing` when the export is `post_ping`) | 404 | `No such procedure` |

Success returns 200 with an empty body. Reducer errors also appear in `spacetime logs`.

### Auth and identity

- **Getting a token without any account:** `POST http://127.0.0.1:3000/v1/identity` (no body) returns
  `{"identity": "<hex>", "token": "<JWT>"}`. The JWT is ES256 with claims
  `hex_identity, sub, iss: "localhost", aud: ["spacetimedb"], iat` and **no `exp`**. It is signed by
  the server key in `<root>/config/id_ecdsa`, so it stays valid until that key changes.
- The CLI's own token (the publisher/owner identity) is `spacetimedb_token` in `<root>/config/cli.toml`.
  The bench uses it (or `$STDB_TOKEN`).
- `POST /v1/identity/websocket-token` without auth returns 401 (not explored further).
- **Without an `Authorization` header the call still succeeds (200)**, but the server mints a new
  anonymous identity per request: `ctx.sender` was a different, random identity each time. So any
  reducer that writes shared state must check `ctx.sender`.
- **Reducers see the caller identity**: `ctx.sender` equalled the bearer token's identity
  (stored in the `ping.sender` column; verified with `spacetime sql`).
- **Service-identity check works**: `init` stores the publisher's `ctx.sender` in a private `service`
  table; `guarded_ping` compares with `svc.identity.equals(ctx.sender)` and throws `SenderError`
  otherwise. Publisher token → 200; a token from `/v1/identity` → 530 `unauthorized sender <hex>`;
  no token → 530. For real services, either share the publisher token with backend services, or mint
  one identity per service via `/v1/identity` and add an owner-only reducer that registers it.

## TS module syntax that worked (spacetimedb 2.13.0)

See `module/src/index.ts`. Key points:

```ts
import { schema, table, t, SenderError } from 'spacetimedb/server';

const ping = table(
  { name: 'ping', public: true },             // public: visible to subscribers
  {
    id: t.u64().primaryKey().autoInc(),       // bigint; insert with id: 0n
    sent_ms: t.f64(),
    payload: t.string(),
    sender: t.identity(),
  }
);
const service = table({ name: 'service', public: false },
  { key: t.u32().primaryKey(), identity: t.identity() });

const spacetimedb = schema({ ping, service }); // ONE object; keys become ctx.db accessors
export default spacetimedb;                    // entry must default-export the schema

export const init = spacetimedb.init(ctx => {  // lifecycle hooks must be exported
  ctx.db.service.insert({ key: 0, identity: ctx.sender });
});

// the export name IS the reducer name (no case conversion): POST .../call/post_ping
export const post_ping = spacetimedb.reducer(
  { sent_ms: t.f64(), payload: t.string() },
  (ctx, { sent_ms, payload }) => {
    ctx.db.ping.insert({ id: 0n, sent_ms, payload, sender: ctx.sender });
  }
);

// guard: ctx.sender is an Identity; compare with .equals(); log with .toHexString()
const svc = ctx.db.service.key.find(0);        // PK accessor = column name
if (!svc || !svc.identity.equals(ctx.sender)) throw new SenderError('unauthorized');

// typed structured args (alternative to one JSON string arg)
const PingIn = t.object('PingIn', { sent_ms: t.f64(), payload: t.string() });
export const post_batch_typed = spacetimedb.reducer({ rows: t.array(PingIn) }, (ctx, { rows }) => { ... });
```

`JSON.parse` works inside reducers (the `post_batch` pattern). The template's agent rules
("Do not pass JSON strings for structured data") recommend typed args instead; both work over HTTP
with similar latency here. The typed form gets argument validation at the boundary (400 on mismatch)
and typed client bindings; the JSON-string form defers validation to the reducer (530 on bad input).

The template `tsconfig.json` (copied from `spacetime init`) is required as-is for `target`, `lib`,
`module`, `isolatedModules`, `noEmit`. `spacetime publish` builds the TS itself (no separate build step).

## TS client subscription API that worked

See `client/src/subscriber.ts`. Runs under Node 22 with `tsx`; Node's global `WebSocket` was enough
(no polyfill).

```ts
import { DbConnection } from './module_bindings/index';   // generated by `spacetime generate`

DbConnection.builder()
  .withUri('ws://127.0.0.1:3000')
  .withDatabaseName('trophy-spike')
  // .withToken(token)            // omit -> server mints an anonymous identity
  // .withConfirmedReads(false)   // lower delivery latency (see results)
  .onConnect((conn, identity, token) => {
    conn.db.ping.onInsert((ctx, row) => { /* row.sentMs, row.payload, row.sender */ });
    conn.subscriptionBuilder()
      .onApplied(ctx => { /* initial rows loaded; ctx.db.ping.count() */ })
      .onError(ctx => { ... })
      .subscribe('SELECT * FROM ping');
  })
  .onConnectError((ctx, err) => { ... })
  .onDisconnect(() => { ... })
  .build();
```

Gotchas:
- **Generated client row fields are camelCase** (`sentMs`, mapped with `.name("sent_ms")`), while the
  module and the HTTP body use the declared snake_case names (`sent_ms`).
- `onInsert` also fires for the rows delivered when the subscription is first applied; the subscriber
  ignores inserts until `onApplied`.
- Private tables (`service`) are left out of generated bindings unless `--include-private`.
- Other builder options seen in the 2.13 typings: `withCompression('gzip'|'brotli'|'none')`,
  `withLightMode`, `withAutomaticReconnect`, `withTokenProvider`, `withWSFn`.

## Files

- `module/`: the TS module (`src/index.ts`) and its `package.json` / `tsconfig.json`.
- `client/`: subscriber (`src/subscriber.ts`) and generated bindings (`src/module_bindings/`).
- `bench/bench.py`: the latency bench (stdlib). `bench/probe_http.py`: HTTP body/auth probe.
- `results/windows11-localhost-2026-10-24.jsonl`: the bench summary lines behind the table.
