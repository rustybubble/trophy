// Gateway client for the dashboard (interfaces-v1 §13). Same-origin under /api, like the PWA.

export interface NewGame {
  game_id: string;
  join_key: string;
  join_url: string;
  t0_ms: number;
}

export interface Session {
  gameId: string;
  joinKey: string;
  joinUrl: string;
  camId: string;
  token: string;
  expMs: number;
  stdb: { uri: string; module: string };
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function req<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body) headers.set("Content-Type", "application/json");
  const res = await fetch(`/api${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: unknown };
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export function createGame(sport: string): Promise<NewGame> {
  return req("/games", { method: "POST", body: JSON.stringify({ sport }) });
}

/** The phones' join link for a game (the PWA reads g and k). */
export function joinLink(gameId: string, joinKey: string, origin: string = location.origin): string {
  return `${origin}/cam/?g=${encodeURIComponent(gameId)}&k=${encodeURIComponent(joinKey)}`;
}

const key = (g: string) => `trophy.dashboard.${g}`;

/** Joins as a display + judge: it reads everything and may approve house rules and resolve challenges. */
export async function joinDashboard(gameId: string, joinKey: string): Promise<Session> {
  try {
    const saved = JSON.parse(localStorage.getItem(key(gameId)) ?? "null") as Session | null;
    if (saved && saved.joinKey === joinKey && saved.expMs > Date.now() + 60_000) return saved;
  } catch {
    /* storage unavailable */
  }
  const r = await req<{
    cam_id: string;
    cam_token: string;
    exp_ms: number;
    stdb: Session["stdb"];
    public_origin?: string;
  }>(`/games/${gameId}/join`, {
    method: "POST",
    body: JSON.stringify({ join_key: joinKey, label: "dashboard", role: "display,judge" }),
  });
  const s: Session = {
    gameId,
    joinKey,
    // the gateway knows the address phones can reach (a public tunnel on networks that isolate devices)
    joinUrl: joinLink(gameId, joinKey, r.public_origin),
    camId: r.cam_id,
    token: r.cam_token,
    expMs: r.exp_ms,
    // Spacetime on the page's own origin: Caddy, a public tunnel and the dev servers all proxy /stdb
    stdb: { ...r.stdb, uri: `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/stdb` },
  };
  try {
    localStorage.setItem(key(gameId), JSON.stringify(s));
  } catch {
    /* the session lasts for this page only */
  }
  return s;
}

export function ctl(s: Session, cmd: string, args: Record<string, unknown> = {}): Promise<{ req_id: string }> {
  return req("/ctl", { method: "POST", body: JSON.stringify({ cmd, args }) }, s.token);
}

// ---- replayed-feed scenarios (D-42, docs/plan/judging-demo.md)
export interface ScenarioSummary {
  id: string;
  title: string;
  sport: string;
  source: string;
  credit: string | null;
  annotated: boolean;
  ready: boolean;
  angles: { label: string; ready: boolean }[];
}

export function listScenarios(s: Session): Promise<ScenarioSummary[]> {
  return req("/scenarios", {}, s.token);
}

export function startScenario(s: Session, scenarioId: string): Promise<{ live_id: string; status: string }> {
  return req(
    `/games/${s.gameId}/scenario`,
    { method: "POST", body: JSON.stringify({ scenario_id: scenarioId }) },
    s.token,
  );
}

export function stopScenario(s: Session): Promise<unknown> {
  return req(`/games/${s.gameId}/scenario/stop`, { method: "POST" }, s.token);
}

/** Server clock minus local clock (ms), from the lowest-latency of a few round trips. */
export async function serverOffsetMs(samples = 5): Promise<number> {
  let best = { rtt: Infinity, off: 0 };
  for (let i = 0; i < samples; i++) {
    const t0 = Date.now();
    const { t_ms } = await req<{ t_ms: number }>("/time");
    const t1 = Date.now();
    if (t1 - t0 < best.rtt) best = { rtt: t1 - t0, off: t_ms - (t0 + t1) / 2 };
  }
  return best.off;
}
