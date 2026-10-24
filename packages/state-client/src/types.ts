import type {
  AiVote,
  Ask,
  Call,
  Camera,
  Challenge,
  Event,
  Game,
  HouseRule,
  Rally,
  Score,
  TrackSample,
} from "@trophy/contracts";

export type {
  AiVote,
  Ask,
  Call,
  Camera,
  Challenge,
  Event,
  Game,
  HouseRule,
  Rally,
  Score,
  TrackSample,
} from "@trophy/contracts";

/** A Spacetime `observation` row, parsed: one trophy.event.v1 event (interfaces-v1 §7.1). */
export type Observation = Event;

export type Unsubscribe = () => void;
export type RowChange = "insert" | "update";

/**
 * The only state API the apps code against (interfaces-v1 §11). Implementations: MockState (labelled
 * synthetic scripts), SpacetimeState (P1), and the OPEN-1 "ws" fallback. Every `on*` call first replays
 * the rows already known (as "insert"), then streams changes.
 */
export interface TrophyState {
  /** True when rows come from a synthetic script; the UI must show `label`. */
  readonly synthetic: boolean;
  readonly label: string | undefined;
  connect(gameId: string): Promise<void>;
  disconnect(): void;
  game(): Game | undefined;
  calls(): Call[];
  scores(): Score[];
  onGame(cb: (g: Game) => void): Unsubscribe;
  onCameras(cb: (c: Camera[]) => void): Unsubscribe;
  onCall(cb: (c: Call, change: RowChange) => void): Unsubscribe;
  onScore(cb: (s: Score[]) => void): Unsubscribe;
  onRally(cb: (r: Rally) => void): Unsubscribe;
  onChallenge(cb: (c: Challenge) => void): Unsubscribe;
  onHouseRule(cb: (h: HouseRule) => void): Unsubscribe;
  onAiVote(cb: (v: AiVote) => void): Unsubscribe;
  onAsk(cb: (a: Ask) => void): Unsubscribe;
  /** World state (D-21): vision observations and the 10 Hz ball track. */
  onObservation(cb: (o: Observation) => void): Unsubscribe;
  onTrackSample(cb: (s: TrackSample) => void): Unsubscribe;
}

export interface TableRows {
  game: Game;
  camera: Camera;
  rally: Rally;
  call: Call;
  score: Score;
  challenge: Challenge;
  house_rule: HouseRule;
  ai_vote: AiVote;
  ask: Ask;
  observation: Observation;
  track_sample: TrackSample;
}
export type TableName = keyof TableRows;

export type MockStep = {
  [T in TableName]: { at_ms: number; table: T; row: TableRows[T] };
}[TableName];

/** trophy.mock_script.v1: a timed list of row upserts. Always synthetic. */
export interface MockScript {
  schema: "trophy.mock_script.v1";
  synthetic: true;
  label: string;
  sport: string;
  game_id: string;
  /** The game's t0_ms in the script; MockState shifts *_ms timestamps so t0 = connect time. */
  t0_ms: number;
  steps: MockStep[];
}
