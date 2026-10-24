// Trophy P0 spike subscriber: subscribes to `SELECT * FROM ping` and logs
// Date.now() - sentMs (column sent_ms; the TS client camelCases it) for every row inserted after the subscription is applied.
//
// Usage: tsx src/subscriber.ts --tag <payload prefix> --expect <rows> [--out file.jsonl]
//        [--uri ws://127.0.0.1:3000] [--db trophy-spike] [--confirmed true|false]
import { appendFileSync, writeFileSync } from 'node:fs';
import { DbConnection } from './module_bindings/index';

function arg(name: string, dflt?: string): string | undefined {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 ? process.argv[i + 1] : dflt;
}
const uri = arg('uri', 'ws://127.0.0.1:3000')!;
const db = arg('db', 'trophy-spike')!;
const tag = arg('tag', '')!;
const expect = Number(arg('expect', '0'));
const out = arg('out');
const confirmed = arg('confirmed');
if (out) writeFileSync(out, '');

const lat: number[] = [];
let applied = false;

function pct(xs: number[], p: number): number {
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.ceil((p / 100) * s.length) - 1)];
}
function finish(code = 0): never {
  if (lat.length) {
    const summary = {
      n: lat.length,
      p50_ms: pct(lat, 50),
      p95_ms: pct(lat, 95),
      max_ms: Math.max(...lat),
      min_ms: Math.min(...lat),
      mean_ms: lat.reduce((a, b) => a + b, 0) / lat.length,
    };
    console.log('SUMMARY ' + JSON.stringify(summary));
  }
  process.exit(code);
}

let builder = DbConnection.builder()
  .withUri(uri)
  .withDatabaseName(db)
  // No token: the server mints a fresh anonymous identity for this subscriber.
  .onConnect((conn, identity, _token) => {
    console.log(`connected as ${identity.toHexString()}`);
    conn.db.ping.onInsert((_ctx, row) => {
      const now = Date.now();
      if (!applied || !row.payload.startsWith(tag)) return;
      const d = now - row.sentMs;
      lat.push(d);
      if (out) appendFileSync(out, JSON.stringify({ id: row.id.toString(), payload: row.payload, sent_ms: row.sentMs, recv_ms: now, lat_ms: d }) + '\n');
      if (expect && lat.length >= expect) finish(0);
    });
    conn
      .subscriptionBuilder()
      .onApplied(ctx => {
        applied = true;
        console.log(`READY subscription applied; ${ctx.db.ping.count()} existing rows`);
      })
      .onError(ctx => {
        console.error('subscription error', ctx.event);
        finish(1);
      })
      .subscribe('SELECT * FROM ping');
  })
  .onConnectError((_ctx, err) => {
    console.error('connect error', err);
    finish(1);
  })
  .onDisconnect(() => console.log('disconnected'));
if (confirmed !== undefined) builder = builder.withConfirmedReads(confirmed === 'true');
builder.build();

process.on('SIGINT', () => finish(0));
setTimeout(() => { console.error(`timeout: got ${lat.length}/${expect}`); finish(2); }, Number(arg('timeout-ms', '120000')));
