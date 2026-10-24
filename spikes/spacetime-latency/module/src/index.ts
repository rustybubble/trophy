// Trophy P0 spike: SpacetimeDB 2.13 reducer -> subscription latency.
// One public table `ping`, reducers post_ping / post_batch (one JSON string arg) /
// post_batch_typed (typed array), and a service-identity check (guarded_ping).
import { schema, table, t, SenderError } from 'spacetimedb/server';

const ping = table(
  { name: 'ping', public: true },
  {
    id: t.u64().primaryKey().autoInc(),
    sent_ms: t.f64(),
    payload: t.string(),
    // ctx.sender of the reducer call, to confirm reducers see the caller identity.
    sender: t.identity(),
  }
);

// Private table: the identity allowed to call guarded reducers (set at publish time by init).
const service = table(
  { name: 'service', public: false },
  { key: t.u32().primaryKey(), identity: t.identity() }
);

const spacetimedb = schema({ ping, service });
export default spacetimedb;

const PingIn = t.object('PingIn', { sent_ms: t.f64(), payload: t.string() });

// init runs once on first publish; ctx.sender is the publishing identity.
export const init = spacetimedb.init(ctx => {
  ctx.db.service.insert({ key: 0, identity: ctx.sender });
});

export const post_ping = spacetimedb.reducer(
  { sent_ms: t.f64(), payload: t.string() },
  (ctx, { sent_ms, payload }) => {
    ctx.db.ping.insert({ id: 0n, sent_ms, payload, sender: ctx.sender });
  }
);

// "One JSON string arg" pattern: batch_json is a JSON array of {sent_ms, payload}.
export const post_batch = spacetimedb.reducer(
  { batch_json: t.string() },
  (ctx, { batch_json }) => {
    let rows: unknown;
    try {
      rows = JSON.parse(batch_json);
    } catch (e) {
      throw new SenderError(`bad JSON: ${String(e)}`);
    }
    if (!Array.isArray(rows)) throw new SenderError('batch_json must be a JSON array');
    for (const r of rows as Array<{ sent_ms: number; payload: string }>) {
      ctx.db.ping.insert({
        id: 0n,
        sent_ms: Number(r.sent_ms),
        payload: String(r.payload),
        sender: ctx.sender,
      });
    }
  }
);

// Typed alternative to the JSON-string pattern.
export const post_batch_typed = spacetimedb.reducer(
  { rows: t.array(PingIn) },
  (ctx, { rows }) => {
    for (const r of rows) {
      ctx.db.ping.insert({ id: 0n, sent_ms: r.sent_ms, payload: r.payload, sender: ctx.sender });
    }
  }
);

// Service-identity check: only the identity recorded by init may call this.
export const guarded_ping = spacetimedb.reducer(
  { sent_ms: t.f64(), payload: t.string() },
  (ctx, { sent_ms, payload }) => {
    const svc = ctx.db.service.key.find(0);
    if (!svc || !svc.identity.equals(ctx.sender)) {
      throw new SenderError(`unauthorized sender ${ctx.sender.toHexString()}`);
    }
    ctx.db.ping.insert({ id: 0n, sent_ms, payload, sender: ctx.sender });
  }
);
