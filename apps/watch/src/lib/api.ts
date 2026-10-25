// Gateway client for Watch (interfaces-v1 §13, §19). Same-origin under /api.
import type { SpriteSpec } from "./moments.ts";

export interface Session {
  gameId: string;
  joinKey: string;
  token: string;
  expMs: number;
  stdb: { uri: string; module: string };
}

export interface ManifestCam {
  cam_id: string;
  hls_url: string;
  t0_game_s: number;
  duration_s: number;
  closed: boolean;
  sprite: SpriteSpec;
}

export interface Manifest {
  game: { game_id: string; status?: string };
  duration_s: number;
  cams: ManifestCam[];
  has_tracks: { ball: boolean; players: boolean };
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

const key = (g: string) => `trophy.watch.${g}`;

/** Joins as a viewer: read-only state plus the watch API (manifest, HLS, sprites, tracks). */
export async function joinViewer(gameId: string, joinKey: string): Promise<Session> {
  try {
    const saved = JSON.parse(localStorage.getItem(key(gameId)) ?? "null") as Session | null;
    if (saved && saved.joinKey === joinKey && saved.expMs > Date.now() + 60_000) return saved;
  } catch {
    /* storage unavailable */
  }
  const r = await req<{ cam_token: string; exp_ms: number; stdb: Session["stdb"] }>(`/games/${gameId}/join`, {
    method: "POST",
    body: JSON.stringify({ join_key: joinKey, label: "watch", role: "viewer" }),
  });
  const s: Session = {
    gameId,
    joinKey,
    token: r.cam_token,
    expMs: r.exp_ms,
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

/** The recorder's manifest, or undefined while there's no recording for the game yet. */
export async function manifest(s: Session): Promise<Manifest | undefined> {
  try {
    return await req<Manifest>(`/watch/${s.gameId}/manifest`, {}, s.token);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return undefined;
    throw e;
  }
}

/** A sprite sheet URL: the manifest's template already carries the token. */
export const spriteUrl = (cam: ManifestCam, sheet: number) => cam.sprite.url_template.replace("{n}", String(sheet));
