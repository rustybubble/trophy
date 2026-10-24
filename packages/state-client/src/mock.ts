import { StateStore } from "./store.ts";
import type { MockScript, MockStep, TableRows, TrophyState } from "./types.ts";

const SHIFTED = new Set(["t0_ms", "created_at_ms", "updated_at_ms", "last_seen_ms", "resolved_at_ms"]);

export interface MockOptions {
  /** Playback speed multiplier (2 = twice as fast). */
  speed?: number;
  /** Restart from the top when the script ends. */
  loop?: boolean;
}

/** Replays a labelled-synthetic MockScript with timers, behaving like a live subscription. */
export class MockState extends StateStore implements TrophyState {
  readonly synthetic = true;
  readonly label: string;
  private timers: ReturnType<typeof setTimeout>[] = [];
  private gameId: string | undefined;
  private shiftMs = 0;

  constructor(
    private readonly script: MockScript,
    private readonly opts: MockOptions = {},
  ) {
    super();
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
    this.put(step.table, row as unknown as TableRows[typeof step.table]);
  }

  private localise(row: Record<string, unknown>): Record<string, unknown> {
    const out: Record<string, unknown> = { ...row };
    if (this.gameId && "game_id" in out) out.game_id = this.gameId;
    for (const k of Object.keys(out)) {
      if (SHIFTED.has(k) && typeof out[k] === "number") out[k] = (out[k] as number) + this.shiftMs;
    }
    return out;
  }
}
