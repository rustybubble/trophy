// Trophy SpacetimeDB module (interfaces-v1 §11, D-21, D-25): the shared world state and game state.
//
// - Every table has typed columns for filtering/display plus `json`: the full contract object
//   (packages/contracts/*.schema.json). Clients read `json` through @trophy/state-client.
// - Every writing reducer takes ONE JSON string argument; over HTTP the body is ["<json text>"].
// - Writers are backend services only. The publisher (owner) registers service identities with a role:
//   vision (observation, track_sample), engine (game state, calls, votes, asks), compiler (house-rule progress).
//   An unauthenticated HTTP call gets a fresh random identity, so every writer checks ctx.sender.
// - Video never goes in here.
import { schema, table, t, SenderError, type InferSchema, type ReducerCtx } from "spacetimedb/server";

// ---------------------------------------------------------------- tables
const owner = table({ name: "owner", public: false }, { key: t.u32().primaryKey(), identity_hex: t.string() });

const service = table(
  { name: "service", public: false },
  { identity_hex: t.string().primaryKey(), role: t.string(), label: t.string() },
);

const game = table(
  { name: "game", public: true },
  {
    game_id: t.string().primaryKey(),
    sport: t.string(),
    status: t.string(),
    period_no: t.u32(),
    rally_no: t.u32(),
    t0_ms: t.f64(),
    updated_at_ms: t.f64(),
    json: t.string(),
  },
);

const camera = table(
  { name: "camera", public: true },
  {
    cam_id: t.string().primaryKey(),
    game_id: t.string().index(),
    label: t.string(),
    role: t.string(),
    connected: t.bool(),
    calib_trusted: t.bool(),
    fps_in: t.f64(),
    sync_err_ms: t.f64(),
    last_seen_ms: t.f64(),
    json: t.string(),
  },
);

const rally = table(
  { name: "rally", public: true },
  {
    rally_key: t.string().primaryKey(), // `${game_id}:${rally_no}`
    game_id: t.string().index(),
    rally_no: t.u32(),
    status: t.string(),
    t_start_s: t.f64(),
    winner_team_id: t.string(),
    json: t.string(),
  },
);

const call = table(
  { name: "call", public: true },
  {
    call_id: t.string().primaryKey(),
    game_id: t.string().index(),
    rally_no: t.u32(),
    t_game_s: t.f64(),
    rule_id: t.string(),
    kind: t.string(),
    outcome: t.string(),
    team_id: t.string(),
    p: t.f64(),
    tier: t.string(),
    status: t.string(),
    text: t.string(),
    created_at_ms: t.f64(),
    json: t.string(),
  },
);

const score = table(
  { name: "score", public: true },
  {
    score_key: t.string().primaryKey(), // `${game_id}:${team_id}`
    game_id: t.string().index(),
    team_id: t.string(),
    points: t.i32(),
    display: t.string(),
    updated_at_ms: t.f64(),
    json: t.string(),
  },
);

const challenge = table(
  { name: "challenge", public: true },
  {
    challenge_id: t.string().primaryKey(),
    game_id: t.string().index(),
    call_id: t.string().index(),
    status: t.string(),
    result: t.string(),
    created_at_ms: t.f64(),
    json: t.string(),
  },
);

const house_rule = table(
  { name: "house_rule", public: true },
  {
    rule_version: t.string().primaryKey(),
    game_id: t.string().index(),
    sport: t.string(),
    status: t.string().index(), // the Droid compiler subscribes to status = 'pending' (§18)
    text: t.string(),
    backend: t.string(),
    updated_at_ms: t.f64(),
    json: t.string(),
  },
);

const ai_vote = table(
  { name: "ai_vote", public: true },
  {
    vote_key: t.string().primaryKey(), // `${call_id}:${backend}` (D-25)
    game_id: t.string().index(),
    call_id: t.string().index(),
    challenge_id: t.string(),
    backend: t.string(),
    choice: t.string(),
    latency_ms: t.f64(),
    json: t.string(),
  },
);

const observation = table(
  { name: "observation", public: true },
  {
    event_id: t.string().primaryKey(),
    game_id: t.string().index(),
    cam_id: t.string(),
    t_game_s: t.f64(),
    sport: t.string(),
    type: t.string(),
    source: t.string(),
    conf: t.f64(),
    json: t.string(),
  },
);

const track_sample = table(
  { name: "track_sample", public: true },
  {
    id: t.u64().primaryKey().autoInc(),
    cam_id: t.string().index(),
    game_id: t.string().index(),
    t_game_s: t.f64(),
    object: t.string(),
    json: t.string(),
  },
);

const ask = table(
  { name: "ask", public: true },
  {
    ask_id: t.string().primaryKey(),
    game_id: t.string().index(),
    question: t.string(),
    answer: t.string(),
    latency_ms: t.f64(),
    created_at_ms: t.f64(),
    json: t.string(),
  },
);

const moment = table(
  { name: "moment", public: true },
  {
    moment_id: t.string().primaryKey(),
    game_id: t.string().index(),
    kind: t.string(),
    t_game_s: t.f64(),
    t_start_s: t.f64(),
    t_end_s: t.f64(),
    label: t.string(),
    highlight_score: t.f64(),
    is_best_play: t.bool(),
    json: t.string(),
  },
);
const commentary = table(
  { name: "commentary", public: true },
  {
    commentary_key: t.string().primaryKey(),
    moment_id: t.string().index(),
    game_id: t.string().index(),
    voice: t.string(),
    text: t.string(),
    validated: t.bool(),
    created_at_ms: t.f64(),
    json: t.string(),
  },
);
const droid_run = table(
  { name: "droid_run", public: true },
  {
    run_id: t.string().primaryKey(),
    game_id: t.string().index(),
    sport: t.string().index(),
    kind: t.string(),
    status: t.string().index(),
    updated_at_ms: t.f64(),
    json: t.string(),
  },
);
const sport_module = table(
  { name: "sport_module", public: true },
  {
    module_key: t.string().primaryKey(),
    sport: t.string().index(),
    game_id: t.string().index(),
    version: t.u32(),
    run_id: t.string(),
    path: t.string(),
    approved_at_ms: t.f64(),
    json: t.string(),
  },
);

const spacetimedb = schema({
  owner,
  service,
  game,
  camera,
  rally,
  call,
  score,
  challenge,
  house_rule,
  ai_vote,
  observation,
  track_sample,
  ask,
  moment,
  commentary,
  droid_run,
  sport_module,
});
export default spacetimedb;

type Ctx = ReducerCtx<InferSchema<typeof spacetimedb>>;
type Obj = Record<string, unknown>;

const TRACK_RETENTION_S = 120;
const ROLES = ["engine", "vision", "compiler"] as const;
type Role = (typeof ROLES)[number];

// ---------------------------------------------------------------- helpers
function parse(json: string): unknown {
  try {
    return JSON.parse(json);
  } catch (e) {
    throw new SenderError(`bad JSON: ${String(e)}`);
  }
}

function parseObj(json: string): Obj {
  const v = parse(json);
  if (!v || typeof v !== "object" || Array.isArray(v)) throw new SenderError("expected a JSON object");
  return v as Obj;
}

function parseArr(json: string): Obj[] {
  const v = parse(json);
  if (!Array.isArray(v)) throw new SenderError("expected a JSON array");
  return v.map((x) => {
    if (!x || typeof x !== "object" || Array.isArray(x)) throw new SenderError("array items must be objects");
    return x as Obj;
  });
}

function str(o: Obj, k: string, required = true): string {
  const v = o[k];
  if (typeof v === "string") return v;
  if (v === undefined || v === null) {
    if (required) throw new SenderError(`missing string field ${k}`);
    return "";
  }
  throw new SenderError(`field ${k} must be a string`);
}

function num(o: Obj, k: string, required = true, dflt = 0): number {
  const v = o[k];
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if ((v === undefined || v === null) && !required) return dflt;
  throw new SenderError(`field ${k} must be a finite number`);
}

function bool(o: Obj, k: string): boolean {
  return o[k] === true;
}

function obj(json: string): Obj {
  return JSON.parse(json) as Obj;
}

function isOwner(ctx: Ctx): boolean {
  const o = ctx.db.owner.key.find(0);
  return !!o && o.identity_hex === ctx.sender.toHexString();
}

function requireRole(ctx: Ctx, ...roles: Role[]): void {
  if (isOwner(ctx)) return;
  const hex = ctx.sender.toHexString();
  const s = ctx.db.service.identity_hex.find(hex);
  if (!s || !(roles as string[]).includes(s.role)) {
    throw new SenderError(`unauthorized: identity ${hex.slice(0, 16)}… needs role ${roles.join("|")}`);
  }
}

// ---------------------------------------------------------------- lifecycle + identities
export const init = spacetimedb.init((ctx) => {
  ctx.db.owner.insert({ key: 0, identity_hex: ctx.sender.toHexString() });
});

/** Owner only. {identity_hex, role: engine|vision|compiler, label?} */
export const register_service = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  if (!isOwner(ctx)) throw new SenderError("only the module owner can register services");
  const o = parseObj(json);
  const identity_hex = str(o, "identity_hex").toLowerCase();
  const role = str(o, "role");
  if (!(ROLES as readonly string[]).includes(role)) throw new SenderError(`role must be one of ${ROLES.join("|")}`);
  const row = { identity_hex, role, label: str(o, "label", false) };
  if (ctx.db.service.identity_hex.find(identity_hex)) ctx.db.service.identity_hex.update(row);
  else ctx.db.service.insert(row);
});

/** Owner only. {identity_hex} */
export const unregister_service = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  if (!isOwner(ctx)) throw new SenderError("only the module owner can unregister services");
  ctx.db.service.identity_hex.delete(str(parseObj(json), "identity_hex").toLowerCase());
});

// ---------------------------------------------------------------- engine: game, cameras, rallies
function writeGame(ctx: Ctx, g: Obj): void {
  const row = {
    game_id: str(g, "game_id"),
    sport: str(g, "sport"),
    status: str(g, "status"),
    period_no: num(g, "period_no", false, 1),
    rally_no: num(g, "rally_no", false, 0),
    t0_ms: num(g, "t0_ms"),
    updated_at_ms: Number(ctx.timestamp.toMillis()),
    json: JSON.stringify(g),
  };
  if (ctx.db.game.game_id.find(row.game_id)) ctx.db.game.game_id.update(row);
  else ctx.db.game.insert(row);
}

/** Engine. A full Game (state.schema.json#/$defs/Game). */
export const upsert_game = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  requireRole(ctx, "engine");
  writeGame(ctx, parseObj(json));
});

/** Engine. A full Camera. */
export const upsert_camera = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  requireRole(ctx, "engine");
  const c = parseObj(json);
  const row = {
    cam_id: str(c, "cam_id"),
    game_id: str(c, "game_id"),
    label: str(c, "label", false),
    role: str(c, "role", false),
    connected: bool(c, "connected"),
    calib_trusted: bool(c, "calib_trusted"),
    fps_in: num(c, "fps_in", false),
    sync_err_ms: num(c, "sync_err_ms", false),
    last_seen_ms: num(c, "last_seen_ms", false),
    json: JSON.stringify(c),
  };
  if (ctx.db.camera.cam_id.find(row.cam_id)) ctx.db.camera.cam_id.update(row);
  else ctx.db.camera.insert(row);
});

function writeRally(ctx: Ctx, r: Obj): void {
  const game_id = str(r, "game_id");
  const rally_no = num(r, "rally_no");
  const row = {
    rally_key: `${game_id}:${rally_no}`,
    game_id,
    rally_no,
    status: str(r, "status"),
    t_start_s: num(r, "t_start_s"),
    winner_team_id: str(r, "winner_team_id", false),
    json: JSON.stringify(r),
  };
  if (ctx.db.rally.rally_key.find(row.rally_key)) ctx.db.rally.rally_key.update(row);
  else ctx.db.rally.insert(row);
  // keep game.rally_no current
  const g = ctx.db.game.game_id.find(game_id);
  if (g && rally_no > g.rally_no) writeGame(ctx, { ...obj(g.json), rally_no });
}

/** Engine. A full Rally with status "open". */
export const open_rally = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  requireRole(ctx, "engine");
  writeRally(ctx, parseObj(json));
});

/** Engine. A full Rally with status "closed" or "voided". */
export const close_rally = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  requireRole(ctx, "engine");
  writeRally(ctx, parseObj(json));
});

// ---------------------------------------------------------------- engine: calls, scores, challenges
function writeCall(ctx: Ctx, c: Obj): void {
  const row = {
    call_id: str(c, "id"),
    game_id: str(c, "game_id"),
    rally_no: num(c, "rally_no", false, 0),
    t_game_s: num(c, "t_game_s"),
    rule_id: str(c, "rule_id"),
    kind: str(c, "kind"),
    outcome: str(c, "outcome"),
    team_id: str(c, "team_id", false),
    p: num(c, "p"),
    tier: str(c, "tier"),
    status: str(c, "status"),
    text: str(c, "text"),
    created_at_ms: num(c, "created_at_ms"),
    json: JSON.stringify(c),
  };
  if (ctx.db.call.call_id.find(row.call_id)) ctx.db.call.call_id.update(row);
  else ctx.db.call.insert(row);
}

function patchCall(ctx: Ctx, call_id: string, patch: Obj): void {
  const existing = ctx.db.call.call_id.find(call_id);
  if (!existing) throw new SenderError(`no call ${call_id}`);
  writeCall(ctx, { ...obj(existing.json), ...patch });
}

/** Engine. A full Call (call.schema.json). Re-posting the same id replaces it. */
export const post_call = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  requireRole(ctx, "engine");
  writeCall(ctx, parseObj(json));
});

/** Engine. {call_id, status, suggested?} */
export const update_call_status = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  requireRole(ctx, "engine");
  const o = parseObj(json);
  const patch: Obj = { status: str(o, "status") };
  if (typeof o.suggested === "string") patch.suggested = o.suggested;
  patchCall(ctx, str(o, "call_id"), patch);
});

/** Engine. A JSON array of Score rows (one per team), written together. */
export const set_score = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  requireRole(ctx, "engine");
  for (const s of parseArr(json)) {
    const game_id = str(s, "game_id");
    const team_id = str(s, "team_id");
    const row = {
      score_key: `${game_id}:${team_id}`,
      game_id,
      team_id,
      points: num(s, "points"),
      display: str(s, "display"),
      updated_at_ms: num(s, "updated_at_ms"),
      json: JSON.stringify(s),
    };
    if (ctx.db.score.score_key.find(row.score_key)) ctx.db.score.score_key.update(row);
    else ctx.db.score.insert(row);
  }
});

function writeChallenge(ctx: Ctx, c: Obj): void {
  const row = {
    challenge_id: str(c, "challenge_id"),
    game_id: str(c, "game_id"),
    call_id: str(c, "call_id"),
    status: str(c, "status"),
    result: str(c, "result", false),
    created_at_ms: num(c, "created_at_ms"),
    json: JSON.stringify(c),
  };
  if (ctx.db.challenge.challenge_id.find(row.challenge_id)) ctx.db.challenge.challenge_id.update(row);
  else ctx.db.challenge.insert(row);
}

/** Engine. A full Challenge (status "open"). Also marks the call challenged and links speculative votes. */
export const open_challenge = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  requireRole(ctx, "engine");
  const c = parseObj(json);
  writeChallenge(ctx, c);
  const call_id = str(c, "call_id");
  patchCall(ctx, call_id, { status: "challenged" });
  for (const v of [...ctx.db.ai_vote.call_id.filter(call_id)]) {
    if (!v.challenge_id) writeVote(ctx, { ...obj(v.json), challenge_id: str(c, "challenge_id") });
  }
});

/** Engine. A full Challenge (status "resolved", result upheld|overturned). Also sets the call status. */
export const resolve_challenge = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  requireRole(ctx, "engine");
  const c = parseObj(json);
  const result = str(c, "result");
  if (result !== "upheld" && result !== "overturned") throw new SenderError("result must be upheld|overturned");
  writeChallenge(ctx, c);
  patchCall(ctx, str(c, "call_id"), { status: result });
});

function writeVote(ctx: Ctx, v: Obj): void {
  const call_id = str(v, "call_id");
  const backend = str(v, "backend");
  let challenge_id = str(v, "challenge_id", false);
  if (!challenge_id) {
    const open = [...ctx.db.challenge.call_id.filter(call_id)].find((c) => c.status === "open");
    if (open) {
      challenge_id = open.challenge_id;
      v = { ...v, challenge_id };
    }
  }
  const row = {
    vote_key: `${call_id}:${backend}`,
    game_id: str(v, "game_id"),
    call_id,
    challenge_id,
    backend,
    choice: str(v, "choice", false),
    latency_ms: num(v, "latency_ms"),
    json: JSON.stringify(v),
  };
  if (ctx.db.ai_vote.vote_key.find(row.vote_key)) ctx.db.ai_vote.vote_key.update(row);
  else ctx.db.ai_vote.insert(row);
}

/** Engine. A full AiVote; challenge_id is filled from an open challenge on the call if missing. */
export const post_ai_vote = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  requireRole(ctx, "engine");
  writeVote(ctx, parseObj(json));
});

// ---------------------------------------------------------------- house rules (§18)
function writeHouseRule(ctx: Ctx, h: Obj): void {
  const row = {
    rule_version: str(h, "rule_version"),
    game_id: str(h, "game_id"),
    sport: str(h, "sport"),
    status: str(h, "status"),
    text: str(h, "text"),
    backend: str(h, "backend", false),
    updated_at_ms: num(h, "updated_at_ms", false, Number(ctx.timestamp.toMillis())),
    json: JSON.stringify(h),
  };
  if (ctx.db.house_rule.rule_version.find(row.rule_version)) ctx.db.house_rule.rule_version.update(row);
  else ctx.db.house_rule.insert(row);
}

/** Engine. A full HouseRule with status "pending": this row is the Droid's trigger. */
export const insert_house_rule = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  requireRole(ctx, "engine");
  const h = parseObj(json);
  if (str(h, "status") !== "pending") throw new SenderError("a new house rule starts as pending");
  if (ctx.db.house_rule.rule_version.find(str(h, "rule_version"))) throw new SenderError("rule_version exists");
  writeHouseRule(ctx, h);
});

const ENGINE_HR_STATUS = ["pending", "approved", "rejected", "failed"];
const COMPILER_HR_STATUS = ["compiling", "ready", "failed"];
const HR_FIELDS = ["plan_md", "steps", "diff", "results", "pack_path", "error", "backend"];

/** Engine. {rule_version, status: pending|approved|rejected|failed, error?, pack_path?} */
export const set_house_rule_status = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  requireRole(ctx, "engine");
  const o = parseObj(json);
  const status = str(o, "status");
  if (!ENGINE_HR_STATUS.includes(status)) throw new SenderError(`engine status must be ${ENGINE_HR_STATUS.join("|")}`);
  const existing = ctx.db.house_rule.rule_version.find(str(o, "rule_version"));
  if (!existing) throw new SenderError("no such house rule");
  const patch: Obj = { status, updated_at_ms: Number(ctx.timestamp.toMillis()) };
  for (const k of ["error", "pack_path"]) if (k in o) patch[k] = o[k];
  writeHouseRule(ctx, { ...obj(existing.json), ...patch });
});

/**
 * Compiler. {rule_version, status?: compiling|ready|failed, plan_md?, steps?, append_steps?, diff?, results?,
 * pack_path?, error?, backend?}. `steps` replaces the list; `append_steps` adds to it (for streaming).
 */
export const update_house_rule_progress = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  requireRole(ctx, "compiler");
  const o = parseObj(json);
  const existing = ctx.db.house_rule.rule_version.find(str(o, "rule_version"));
  if (!existing) throw new SenderError("no such house rule");
  if (existing.status === "approved" || existing.status === "rejected") {
    throw new SenderError(`house rule is already ${existing.status}`);
  }
  const cur = obj(existing.json);
  const patch: Obj = { updated_at_ms: Number(ctx.timestamp.toMillis()) };
  if ("status" in o) {
    const status = str(o, "status");
    if (!COMPILER_HR_STATUS.includes(status)) {
      throw new SenderError(`compiler status must be ${COMPILER_HR_STATUS.join("|")}`);
    }
    patch.status = status;
  }
  for (const k of HR_FIELDS) if (k in o) patch[k] = o[k];
  if (Array.isArray(o.append_steps)) {
    const steps = Array.isArray(patch.steps) ? patch.steps : Array.isArray(cur.steps) ? cur.steps : [];
    patch.steps = [...steps, ...o.append_steps];
  }
  writeHouseRule(ctx, { ...cur, ...patch });
});

// ---------------------------------------------------------------- ask the ref
/** Engine. A full Ask row (from the gateway's ask_logged command). */
export const post_ask = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  requireRole(ctx, "engine");
  const a = parseObj(json);
  const row = {
    ask_id: str(a, "ask_id"),
    game_id: str(a, "game_id"),
    question: str(a, "question"),
    answer: str(a, "answer"),
    latency_ms: num(a, "latency_ms"),
    created_at_ms: num(a, "created_at_ms"),
    json: JSON.stringify(a),
  };
  if (ctx.db.ask.ask_id.find(row.ask_id)) ctx.db.ask.ask_id.update(row);
  else ctx.db.ask.insert(row);
});

// ---------------------------------------------------------------- vision: the world state (D-21)
/** Vision. A JSON array of trophy.event.v1 events (trophy.world.ObservationWriter). */
export const post_observations = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  requireRole(ctx, "vision");
  for (const e of parseArr(json)) {
    const cams = Array.isArray(e.cams) ? e.cams : [];
    const row = {
      event_id: str(e, "id"),
      game_id: str(e, "game_id"),
      cam_id: typeof cams[0] === "string" ? cams[0] : "",
      t_game_s: num(e, "t_game_s"),
      sport: str(e, "sport"),
      type: str(e, "type"),
      source: str(e, "source"),
      conf: num(e, "conf"),
      json: JSON.stringify(e),
    };
    if (ctx.db.observation.event_id.find(row.event_id)) ctx.db.observation.event_id.update(row);
    else ctx.db.observation.insert(row);
  }
});

/** Vision. A JSON array of TrackSample rows (10 Hz). Keeps the last TRACK_RETENTION_S per camera. */
export const post_track_samples = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  requireRole(ctx, "vision");
  const newest = new Map<string, number>();
  for (const s of parseArr(json)) {
    const cam_id = str(s, "cam_id");
    const t_game_s = num(s, "t_game_s");
    ctx.db.track_sample.insert({
      id: 0n,
      cam_id,
      game_id: str(s, "game_id"),
      t_game_s,
      object: str(s, "object", false) || "ball",
      json: JSON.stringify(s),
    });
    newest.set(cam_id, Math.max(newest.get(cam_id) ?? -Infinity, t_game_s));
  }
  for (const [cam_id, t_new] of newest) pruneCam(ctx, cam_id, t_new - TRACK_RETENTION_S);
});

function pruneCam(ctx: Ctx, cam_id: string, before_t: number): number {
  let n = 0;
  for (const r of [...ctx.db.track_sample.cam_id.filter(cam_id)]) {
    if (r.t_game_s < before_t) {
      ctx.db.track_sample.id.delete(r.id);
      n++;
    }
  }
  return n;
}

/** Engine. {cam_id, before_t_game_s}: explicit prune (e.g. at game end). */
export const prune_track_samples = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  requireRole(ctx, "engine");
  const o = parseObj(json);
  pruneCam(ctx, str(o, "cam_id"), num(o, "before_t_game_s"));
});

// ---------------------------------------------------------------- post-game metadata and compiler runs
function oneOf(o: Obj, key: string, values: readonly string[]): string {
  const v = str(o, key);
  if (!values.includes(v)) throw new SenderError(`${key} must be ${values.join("|")}`);
  return v;
}
function strings(o: Obj, key: string): string[] {
  const v = o[key];
  if (!Array.isArray(v) || v.some((x) => typeof x !== "string")) throw new SenderError(`${key} must be a string array`);
  return v as string[];
}
function boolean(o: Obj, key: string): boolean {
  if (typeof o[key] !== "boolean") throw new SenderError(`${key} must be a boolean`);
  return o[key] as boolean;
}
function record(o: Obj, key: string): Obj {
  const v = o[key];
  if (!v || typeof v !== "object" || Array.isArray(v)) throw new SenderError(`${key} must be an object`);
  return v as Obj;
}
function integer(o: Obj, key: string, min: number): number {
  const v = num(o, key);
  if (!Number.isInteger(v) || v < min) throw new SenderError(`${key} must be an integer >= ${min}`);
  return v;
}
function writeMoment(ctx: Ctx, m: Obj): void {
  const kind = oneOf(m, "kind", [
    "point",
    "serve_fault",
    "edge",
    "challenge",
    "basket",
    "bookmark",
    "house_rule",
    "rally",
  ]);
  const t_start_s = num(m, "t_start_s"),
    t_end_s = num(m, "t_end_s");
  if (t_end_s < t_start_s) throw new SenderError("moment ends before it starts");
  const highlight_score = num(m, "highlight_score");
  if (highlight_score < 0 || highlight_score > 1) throw new SenderError("highlight_score outside [0,1]");
  strings(m, "tags");
  strings(m, "reasons");
  str(m, "score_after");
  num(m, "thumb_t_s");
  const label = str(m, "label");
  if (label.length > 80) throw new SenderError("label exceeds 80 characters");
  const row = {
    moment_id: str(m, "moment_id"),
    game_id: str(m, "game_id"),
    kind,
    t_game_s: num(m, "t_game_s"),
    t_start_s,
    t_end_s,
    label,
    highlight_score,
    is_best_play: boolean(m, "is_best_play"),
    json: JSON.stringify(m),
  };
  const old = ctx.db.moment.moment_id.find(row.moment_id);
  if (old && old.game_id !== row.game_id) throw new SenderError("moment game_id is immutable");
  if (old) ctx.db.moment.moment_id.update(row);
  else ctx.db.moment.insert(row);
}
/** Engine. Full Moment, idempotently replaced. */
export const upsert_moment = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  requireRole(ctx, "engine");
  const m = parseObj(json);
  // Preserve a single best play even when a caller re-posts an old snapshot.
  if (m.is_best_play === true)
    for (const r of [...ctx.db.moment.game_id.filter(str(m, "game_id"))]) {
      if (r.is_best_play && r.moment_id !== m.moment_id) writeMoment(ctx, { ...obj(r.json), is_best_play: false });
    }
  writeMoment(ctx, m);
});
/** Engine. {game_id, moment_id, reasons}; target must belong to this game. */
export const set_best_play = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  requireRole(ctx, "engine");
  const o = parseObj(json),
    game_id = str(o, "game_id"),
    moment_id = str(o, "moment_id");
  const reasons = strings(o, "reasons"),
    target = ctx.db.moment.moment_id.find(moment_id);
  if (!target || target.game_id !== game_id) throw new SenderError("no such moment in this game");
  for (const r of [...ctx.db.moment.game_id.filter(game_id)]) {
    if (r.is_best_play || r.moment_id === moment_id)
      writeMoment(ctx, {
        ...obj(r.json),
        is_best_play: r.moment_id === moment_id,
        ...(r.moment_id === moment_id ? { reasons } : {}),
      });
  }
});
/** Engine. Full Commentary; one row per (moment_id, voice), so both voices survive. */
export const post_commentary = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  requireRole(ctx, "engine");
  const c = parseObj(json),
    moment_id = str(c, "moment_id"),
    game_id = str(c, "game_id");
  const m = ctx.db.moment.moment_id.find(moment_id);
  if (!m || m.game_id !== game_id) throw new SenderError("no such moment in this game");
  const voice = oneOf(c, "voice", ["pbp", "colour"]);
  record(c, "facts");
  oneOf(c, "source", ["claude", "template"]);
  const row = {
    commentary_key: JSON.stringify([moment_id, voice]),
    moment_id,
    game_id,
    voice,
    text: str(c, "text"),
    validated: boolean(c, "validated"),
    created_at_ms: num(c, "created_at_ms"),
    json: JSON.stringify(c),
  };
  if (ctx.db.commentary.commentary_key.find(row.commentary_key)) ctx.db.commentary.commentary_key.update(row);
  else ctx.db.commentary.insert(row);
});
function writeDroidRun(ctx: Ctx, o: Obj): void {
  oneOf(o, "schema", ["trophy.droid_run.v1"]);
  oneOf(o, "backend", ["droid", "claude-fallback"]);
  record(o, "trigger");
  str(o, "model");
  str(o, "plan_md");
  str(o, "diff");
  if (!Array.isArray(o.steps)) throw new SenderError("steps must be an array");
  integer(o, "attempt", 0);
  integer(o, "max_attempts", 1);
  num(o, "started_at_ms");
  if (!("results" in o) || (o.results !== null && (typeof o.results !== "object" || Array.isArray(o.results)))) {
    throw new SenderError("results must be an object or null");
  }
  const row = {
    run_id: str(o, "run_id"),
    game_id: str(o, "game_id", false),
    sport: str(o, "sport"),
    kind: oneOf(o, "kind", ["compile", "house_rule", "retune"]),
    status: oneOf(o, "status", ["queued", "running", "ready", "failed", "approved", "rejected"]),
    updated_at_ms: num(o, "updated_at_ms"),
    json: JSON.stringify(o),
  };
  if (ctx.db.droid_run.run_id.find(row.run_id)) ctx.db.droid_run.run_id.update(row);
  else ctx.db.droid_run.insert(row);
}
/** Compiler. Full DroidRun snapshot, never approval/rejection. */
export const update_droid_run = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  requireRole(ctx, "compiler");
  const o = parseObj(json);
  oneOf(o, "status", ["queued", "running", "ready", "failed"]);
  const old = ctx.db.droid_run.run_id.find(str(o, "run_id"));
  if (old) {
    if (["approved", "rejected"].includes(old.status)) throw new SenderError("run is already final");
    if (old.sport !== str(o, "sport") || old.game_id !== str(o, "game_id", false) || old.kind !== str(o, "kind")) {
      throw new SenderError("run identity is immutable");
    }
    if (num(o, "updated_at_ms") < old.updated_at_ms) throw new SenderError("stale run snapshot");
  }
  writeDroidRun(ctx, o);
});
/** Engine. {run_id, status: approved|rejected, error?}; approval requires a ready, passing run. */
export const set_droid_run_status = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  requireRole(ctx, "engine");
  const o = parseObj(json),
    status = oneOf(o, "status", ["approved", "rejected"]);
  const old = ctx.db.droid_run.run_id.find(str(o, "run_id"));
  if (!old) throw new SenderError("no such run");
  if (old.status === status) return;
  if (["approved", "rejected"].includes(old.status)) throw new SenderError("run is already final");
  const cur = obj(old.json);
  if (
    status === "approved" &&
    (old.status !== "ready" || record(cur, "results").passed !== true || !str(cur, "commit", false))
  ) {
    throw new SenderError("approval requires ready status, passing results and a commit");
  }
  writeDroidRun(ctx, {
    ...cur,
    status,
    ...(o.error !== undefined ? { error: str(o, "error") } : {}),
    updated_at_ms: Number(ctx.timestamp.toMillis()),
  });
});
/** Engine. Full SportModuleRow; per-game modules don't overwrite a base module. */
export const upsert_sport_module = spacetimedb.reducer({ json: t.string() }, (ctx, { json }) => {
  requireRole(ctx, "engine");
  const o = parseObj(json),
    sport = str(o, "sport"),
    game_id = str(o, "game_id", false);
  const backend = oneOf(o, "backend", ["droid", "claude-fallback", "handwritten"]);
  const run_id = str(o, "run_id"),
    version = integer(o, "version", 1);
  if (backend !== "handwritten") {
    const run = ctx.db.droid_run.run_id.find(run_id);
    if (
      !run ||
      run.status !== "approved" ||
      run.sport !== sport ||
      run.game_id !== game_id ||
      str(obj(run.json), "commit") !== str(o, "commit")
    ) {
      throw new SenderError("module requires a matching approved run and commit");
    }
  }
  const row = {
    module_key: JSON.stringify([game_id, sport]),
    sport,
    game_id,
    version,
    run_id,
    path: str(o, "path"),
    approved_at_ms: num(o, "approved_at_ms"),
    json: JSON.stringify(o),
  };
  const old = ctx.db.sport_module.module_key.find(row.module_key);
  if (old && version <= old.version && old.json !== row.json) throw new SenderError("module version must increase");
  if (old) ctx.db.sport_module.module_key.update(row);
  else ctx.db.sport_module.insert(row);
});
