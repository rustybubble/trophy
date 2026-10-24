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
};

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
    return new Promise<void>((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error(`Spacetime subscription not applied within ${this.opts.timeoutMs ?? 10000} ms`)),
        this.opts.timeoutMs ?? 10000,
      );
      // The SDK resolves "v1/database/..." relative to the URI, so a path prefix (wss://trophy.photo/stdb behind
      // Caddy) needs a trailing slash or it is dropped.
      const uri = this.opts.uri.endsWith("/") ? this.opts.uri : `${this.opts.uri}/`;
      this.conn = DbConnection.builder()
        .withUri(uri)
        .withDatabaseName(this.opts.module)
        .onConnect((conn) => {
          const db = conn.db as unknown as Record<string, TableHandle>;
          for (const table of Object.keys(ACCESSORS) as TableName[]) {
            const h = db[ACCESSORS[table]]!;
            const put = (row: JsonRow) => this.put(table, JSON.parse(row.json) as TableRows[typeof table]);
            h.onInsert((_ctx, row) => put(row));
            h.onUpdate((_ctx, _old, row) => put(row));
            h.onDelete((_ctx, row) => this.drop(table, JSON.parse(row.json) as TableRows[typeof table]));
          }
          // gameId is validated above, so interpolating it into SQL is safe
          const where = `WHERE game_id = '${gameId}'`;
          conn
            .subscriptionBuilder()
            .onApplied(() => {
              clearTimeout(timer);
              resolve();
            })
            .onError((ctx) => {
              clearTimeout(timer);
              reject(new Error(`Spacetime subscription error: ${String((ctx as { event?: unknown }).event)}`));
            })
            .subscribe(Object.keys(ACCESSORS).map((t) => `SELECT * FROM ${t} ${where}`));
        })
        .onConnectError((_ctx, err) => {
          clearTimeout(timer);
          reject(err instanceof Error ? err : new Error(String(err)));
        })
        .build();
    });
  }

  disconnect(): void {
    this.conn?.disconnect();
    this.conn = undefined;
  }
}
