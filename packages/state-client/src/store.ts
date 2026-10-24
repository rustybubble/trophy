import type {
  AiVote,
  Ask,
  Call,
  Camera,
  Challenge,
  Game,
  HouseRule,
  Observation,
  Rally,
  RowChange,
  Score,
  TableName,
  TableRows,
  TrackSample,
  Unsubscribe,
} from "./types.ts";

export const ROW_KEY: { [T in TableName]: (r: TableRows[T]) => string } = {
  game: (r) => r.game_id,
  camera: (r) => r.cam_id,
  rally: (r) => `${r.game_id}/${r.rally_no}`,
  call: (r) => r.id,
  score: (r) => `${r.game_id}/${r.team_id}`,
  challenge: (r) => r.challenge_id,
  house_rule: (r) => r.rule_version,
  ai_vote: (r) => `${r.call_id}/${r.backend}`,
  ask: (r) => r.ask_id,
  observation: (r) => r.id,
  track_sample: (r) => `${r.cam_id}/${r.t_game_s}`,
};

type Listener = (row: never, change: RowChange) => void;

/**
 * The row cache + listener fan-out shared by every TrophyState implementation. Subclasses feed it with
 * `put` / `drop`; every `on*` first replays the rows already known (as "insert"), then streams changes.
 */
export abstract class StateStore {
  protected tables = new Map<TableName, Map<string, unknown>>();
  private listeners = new Map<TableName, Set<Listener>>();

  protected put<T extends TableName>(table: T, row: TableRows[T]): void {
    let t = this.tables.get(table);
    if (!t) this.tables.set(table, (t = new Map()));
    const key = (ROW_KEY[table] as (r: TableRows[T]) => string)(row);
    const change: RowChange = t.has(key) ? "update" : "insert";
    t.set(key, row);
    for (const l of this.listeners.get(table) ?? []) l(row as never, change);
  }

  /** Forget a row (e.g. a pruned track sample). Listeners aren't told: the interface has no deletes. */
  protected drop<T extends TableName>(table: T, row: TableRows[T]): void {
    this.tables.get(table)?.delete((ROW_KEY[table] as (r: TableRows[T]) => string)(row));
  }

  protected rows<T extends TableName>(table: T): TableRows[T][] {
    return [...(this.tables.get(table)?.values() ?? [])] as TableRows[T][];
  }

  private on<T extends TableName>(table: T, cb: (row: TableRows[T], change: RowChange) => void): Unsubscribe {
    let set = this.listeners.get(table);
    if (!set) this.listeners.set(table, (set = new Set()));
    const l = cb as unknown as Listener;
    set.add(l);
    for (const r of this.rows(table)) cb(r, "insert");
    return () => set.delete(l);
  }

  /** Fires `cb` with the whole table whenever any row in it changes. */
  private onList<T extends TableName>(table: T, cb: (rows: TableRows[T][]) => void): Unsubscribe {
    const existing = this.rows(table);
    if (existing.length) cb(existing);
    let set = this.listeners.get(table);
    if (!set) this.listeners.set(table, (set = new Set()));
    const l: Listener = () => cb(this.rows(table));
    set.add(l);
    return () => set.delete(l);
  }

  game(): Game | undefined {
    return this.rows("game")[0];
  }
  calls(): Call[] {
    return this.rows("call");
  }
  scores(): Score[] {
    return this.rows("score");
  }
  onGame(cb: (g: Game) => void): Unsubscribe {
    return this.on("game", (g) => cb(g));
  }
  onCameras(cb: (c: Camera[]) => void): Unsubscribe {
    return this.onList("camera", cb);
  }
  onCall(cb: (c: Call, change: RowChange) => void): Unsubscribe {
    return this.on("call", cb);
  }
  onScore(cb: (s: Score[]) => void): Unsubscribe {
    return this.onList("score", cb);
  }
  onRally(cb: (r: Rally) => void): Unsubscribe {
    return this.on("rally", (r) => cb(r));
  }
  onChallenge(cb: (c: Challenge) => void): Unsubscribe {
    return this.on("challenge", (c) => cb(c));
  }
  onHouseRule(cb: (h: HouseRule) => void): Unsubscribe {
    return this.on("house_rule", (h) => cb(h));
  }
  onAiVote(cb: (v: AiVote) => void): Unsubscribe {
    return this.on("ai_vote", (v) => cb(v));
  }
  onAsk(cb: (a: Ask) => void): Unsubscribe {
    return this.on("ask", (a) => cb(a));
  }
  onObservation(cb: (o: Observation) => void): Unsubscribe {
    return this.on("observation", (o) => cb(o));
  }
  onTrackSample(cb: (s: TrackSample) => void): Unsubscribe {
    return this.on("track_sample", (s) => cb(s));
  }
}
