import { DbConnection } from "./bindings/index.ts";
import { StateStore } from "./store.ts";
import type { TableName, TableRows, TrophyState } from "./types.ts";

const GAME_ID_RE = /^g_[0-9a-hjkmnp-tv-z]{8}$/;

/** Spacetime table name -> generated accessor on `conn.db`. Every row carries the full contract object in `json`. */
const ACCESSORS: { [T in TableName]: string } = {
  game: "game",
  camera: "camera",
  rally: "rally",
  call: "call",
  score: "score",
  challenge: "challenge",
  house_rule: "houseRule",
  ai_vote: "aiVote",
  ask: "ask",
  observation: "observation",
  track_sample: "trackSample",
  moment: "moment",
  commentary: "commentary",
  feed: "feed",
  viewer: "viewer",
  droid_run: "droidRun",
};
/** Tables added after the first module (#10, D-42, D-43). Subscribed separately, so an older module still serves live games. */
const POST_GAME: TableName[] = ["moment", "commentary", "feed", "viewer", "droid_run"];

type JsonRow = { json: string };
interface TableHandle {
  onInsert(cb: (ctx: unknown, row: JsonRow) => void): void;
  onUpdate(cb: (ctx: unknown, oldRow: JsonRow, row: JsonRow) => void): void;
  onDelete(cb: (ctx: unknown, row: JsonRow) => void): void;
}

export interface SpacetimeOptions {
  /** e.g. ws://127.0.0.1:3000, or wss://trophy.photo/stdb behind Caddy */
  uri: string;
  /** database name, e.g. trophy */
  module: string;
  /** reject connect() if the subscription isn't applied within this many ms */
  timeoutMs?: number;
}

/** TrophyState over the live Spacetime module (interfaces-v1 §11). Read-only: clients write through the gateway. */
export class SpacetimeState extends StateStore implements TrophyState {
  private conn: DbConnection | undefined;
  private generation = 0;
  private retryTimer: ReturnType<typeof setTimeout> | undefined;

  constructor(private readonly opts: SpacetimeOptions) {
    super();
  }

  /** Seeded/demo games set params.synthetic; the UI must label them. */
  get synthetic(): boolean {
    return this.game()?.params?.synthetic === true;
  }
  get label(): string | undefined {
    const label = this.game()?.params?.label;
    return this.synthetic ? (typeof label === "string" ? label : "SYNTHETIC") : undefined;
  }

  connect(gameId: string): Promise<void> {
    if (!GAME_ID_RE.test(gameId)) return Promise.reject(new Error(`bad game_id ${JSON.stringify(gameId)}`));
    this.disconnect();
    this.tables.clear();
    const generation = this.generation;
    const timeoutMs = this.opts.timeoutMs ?? 10000;
    // The SDK resolves "v1/database/..." relative to the URI, so a path prefix (wss://trophy.photo/stdb behind
    // Caddy) needs a trailing slash or it is dropped.
    const uri = this.opts.uri.endsWith("/") ? this.opts.uri : `${this.opts.uri}/`;
    return new Promise<void>((resolve, reject) => {
      let settled = false;
      let lastError: string | undefined;
      const settle = (err?: Error) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        if (err) reject(err);
        else resolve();
      };
      // A slow subscription or an unreachable socket rejects here, but the attempts below keep going: rows that
      // arrive later still reach the store (the apps clear their error when the game row shows up).
      const timer = setTimeout(
        () =>
          settle(
            new Error(
              lastError
                ? `Can't open the Spacetime socket at ${uri} (${lastError}); still retrying`
                : `Spacetime subscription not applied within ${timeoutMs} ms`,
            ),
          ),
        timeoutMs,
      );
      // A dropped socket (a tunnel or Wi-Fi hiccup) used to leave the page without live state until a reload: the
      // SDK now reconnects an established session and replays its subscriptions, and a failed first attempt (or a
      // session the SDK gave up on) starts a new connection after a backoff.
      const attempt = (n: number) => {
        if (generation !== this.generation) return;
        let established = false;
        const retry = (err: unknown) => {
          if (generation !== this.generation || this.conn !== conn) return;
          lastError = err instanceof Error ? err.message : String(err ?? "connection closed");
          this.conn = undefined;
          this.retryTimer = setTimeout(() => attempt(n + 1), Math.min(500 * 2 ** n, 5000));
        };
        const conn: DbConnection = DbConnection.builder()
          .withUri(uri)
          .withDatabaseName(this.opts.module)
          .withAutomaticReconnect()
          .onConnect((c) => {
            established = true;
            const db = c.db as unknown as Record<string, TableHandle>;
            for (const table of Object.keys(ACCESSORS) as TableName[]) {
              const h = db[ACCESSORS[table]]!;
              const put = (row: JsonRow) => this.put(table, JSON.parse(row.json) as TableRows[typeof table]);
              h.onInsert((_ctx, row) => put(row));
              h.onUpdate((_ctx, _old, row) => put(row));
              h.onDelete((_ctx, row) => this.drop(table, JSON.parse(row.json) as TableRows[typeof table]));
            }
            // gameId is validated above, so interpolating it into SQL is safe
            const where = `WHERE game_id = '${gameId}'`;
            c.subscriptionBuilder()
              .onApplied(() => settle())
              .onError((ctx) =>
                settle(new Error(`Spacetime subscription error: ${String((ctx as { event?: unknown }).event)}`)),
              )
              .subscribe(
                (Object.keys(ACCESSORS) as TableName[])
                  .filter((t) => !POST_GAME.includes(t))
                  .map((t) => `SELECT * FROM ${t} ${where}`),
              );
            c.subscriptionBuilder()
              .onError((ctx) =>
                console.warn(`Trophy: post-game tables unavailable (${String((ctx as { event?: unknown }).event)})`),
              )
              .subscribe(POST_GAME.map((t) => `SELECT * FROM ${t} ${where}`));
          })
          // nextAttempt is set while the SDK is reconnecting an established session; undefined means it won't retry
          .onConnectError((_ctx, err, nextAttempt?: number) => {
            if (!established || nextAttempt === undefined) retry(err);
          })
          .onDisconnect((_ctx, err?: Error, nextAttempt?: number) => {
            if (nextAttempt === undefined) retry(err);
          })
          .build();
        this.conn = conn;
      };
      attempt(0);
    });
  }

  disconnect(): void {
    this.generation++;
    clearTimeout(this.retryTimer);
    this.conn?.disconnect();
    this.conn = undefined;
  }
}
