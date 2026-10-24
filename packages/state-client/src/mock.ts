import type {
  AiVote,
  Ask,
  Call,
  Camera,
  Challenge,
  Game,
  HouseRule,
  MockScript,
  MockStep,
  Observation,
  Rally,
  RowChange,
  Score,
  TableName,
  TableRows,
  TrackSample,
  TrophyState,
  Unsubscribe,
} from "./types.ts";

const KEY: { [T in TableName]: (r: TableRows[T]) => string } = {
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

const SHIFTED = new Set(["t0_ms", "created_at_ms", "updated_at_ms", "last_seen_ms", "resolved_at_ms"]);

export interface MockOptions {
  /** Playback speed multiplier (2 = twice as fast). */
  speed?: number;
  /** Restart from the top when the script ends. */
  loop?: boolean;
}

type Listener = (row: never, change: RowChange) => void;

/** Replays a labelled-synthetic MockScript with timers, behaving like a live subscription. */
export class MockState implements TrophyState {
  readonly synthetic = true;
  readonly label: string;
  private tables = new Map<TableName, Map<string, unknown>>();
  private listeners = new Map<TableName, Set<Listener>>();
  private timers: ReturnType<typeof setTimeout>[] = [];
  private gameId: string | undefined;
  private shiftMs = 0;

  constructor(
    private readonly script: MockScript,
    private readonly opts: MockOptions = {},
  ) {
    if (!script.synthetic) throw new Error("MockState only plays scripts labelled synthetic");
    this.label = script.label;
  }

  connect(gameId: string): Promise<void> {
    this.disconnect();
    this.gameId = gameId || this.script.game_id;
    this.shiftMs = Date.now() - this.script.t0_ms;
    this.schedule();
    return Promise.resolve();
  }

  disconnect(): void {
    this.timers.forEach(clearTimeout);
    this.timers = [];
  }

  private schedule(): void {
    const speed = this.opts.speed ?? 1;
    const steps = [...this.script.steps].sort((a, b) => a.at_ms - b.at_ms);
    for (const step of steps) {
      this.timers.push(setTimeout(() => this.apply(step), step.at_ms / speed));
    }
    if (this.opts.loop && steps.length) {
      const end = steps[steps.length - 1]!.at_ms / speed + 3000 / speed;
      this.timers.push(
        setTimeout(() => {
          this.tables.clear();
          this.shiftMs = Date.now() - this.script.t0_ms;
          this.timers = [];
          this.schedule();
        }, end),
      );
    }
  }

  private apply(step: MockStep): void {
    const row = this.localise(step.row as unknown as Record<string, unknown>);
    const table = step.table;
    let t = this.tables.get(table);
    if (!t) this.tables.set(table, (t = new Map()));
    const key = (KEY[table] as (r: unknown) => string)(row);
    const change: RowChange = t.has(key) ? "update" : "insert";
    t.set(key, row);
    for (const l of this.listeners.get(table) ?? []) l(row as never, change);
  }

  private localise(row: Record<string, unknown>): Record<string, unknown> {
    const out: Record<string, unknown> = { ...row };
    if (this.gameId && "game_id" in out) out.game_id = this.gameId;
    for (const k of Object.keys(out)) {
      if (SHIFTED.has(k) && typeof out[k] === "number") out[k] = (out[k] as number) + this.shiftMs;
    }
    return out;
  }

  private rows<T extends TableName>(table: T): TableRows[T][] {
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
