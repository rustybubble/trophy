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
export function joinLink(gameId: string, joinKey: string): string {
  return `${location.origin}/cam/?g=${encodeURIComponent(gameId)}&k=${encodeURIComponent(joinKey)}`;
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
  const r = await req<{ cam_id: string; cam_token: string; exp_ms: number; stdb: Session["stdb"] }>(
    `/games/${gameId}/join`,
    { method: "POST", body: JSON.stringify({ join_key: joinKey, label: "dashboard", role: "display,judge" }) },
  );
  const s: Session = {
    gameId,
    joinKey,
    joinUrl: joinLink(gameId, joinKey),
    camId: r.cam_id,
    token: r.cam_token,
    expMs: r.exp_ms,
    // on a local dev origin, reach Spacetime through the dev server's /stdb proxy
    stdb: /^(127\.0\.0\.1|localhost)$/.test(location.hostname)
      ? { ...r.stdb, uri: `ws://${location.host}/stdb` }
      : r.stdb,
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

/** Trophy Watch for this game: the Vite dev server on 5175 on a local origin, /watch/ behind Caddy. */
export function watchLink(gameId: string, joinKey: string): string {
  const q = `?g=${encodeURIComponent(gameId)}&k=${encodeURIComponent(joinKey)}`;
  const local = /^(127\.0\.0\.1|localhost)$/.test(location.hostname);
  return local ? `${location.protocol}//${location.hostname}:5175/watch/${q}` : `${location.origin}/watch/${q}`;
}

/** The referee's own recording of a window on one camera (the recorder's archive), cut by the gateway. */
export function replayClipUrl(s: Session, camId: string, t0: number, t1: number): string {
  const q = new URLSearchParams({ cam: camId, t0: t0.toFixed(3), t1: t1.toFixed(3), token: s.token });
  return `/api/replay/${s.gameId}/clip?${q}`;
}

export interface Overlay {
  marks: {
    t_game_s: number;
    px: number[];
    ellipse_px: { cx: number; cy: number; rx: number; ry: number; angle_rad: number };
  }[];
  warnings: string[];
}

/** The call's bounce marks and their σ ellipses projected onto that camera's frame (source pixels, 1280×720). */
export function replayOverlay(s: Session, camId: string, t0: number, t1: number, callId: string): Promise<Overlay> {
  const q = new URLSearchParams({ cam: camId, t0: t0.toFixed(3), t1: t1.toFixed(3), call_id: callId });
  return req(`/replay/${s.gameId}/overlay?${q}`, {}, s.token);
}
