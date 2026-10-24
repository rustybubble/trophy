// Gateway client (interfaces-v1 §13). Everything is same-origin under /api.
import type { Calibration, CalibrationRequest } from "@trophy/contracts";

export type Role = "cam" | "display" | "judge";

export interface Session {
  gameId: string;
  camId: string;
  token: string;
  expMs: number;
  role: string;
  t0Ms: number;
  stdb: { uri: string; module: string };
  frame: { w: number; h: number; fps: number; quality: number };
}

export interface VoiceToken {
  access_token: string;
  expires_at_ms: number;
  cartesia_version: string;
  voices: { calls: string; ref: string };
}

export interface AskAnswer {
  answer: string;
  speech?: string;
  citations: { rule_id: string; title: string; url: string; quote: string }[];
  latency_ms: number;
  moss_ms?: number;
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
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
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

const storeKey = (g: string) => `trophy.session.${g}`;
const camKey = (g: string) => `trophy.cam.${g}`; // interfaces-v1 §1

export function savedSession(gameId: string): Session | undefined {
  try {
    const s = JSON.parse(localStorage.getItem(storeKey(gameId)) ?? "null") as Session | null;
    return s && s.expMs > Date.now() + 60_000 ? s : undefined;
  } catch {
    return undefined;
  }
}

export function forgetSession(gameId: string): void {
  try {
    localStorage.removeItem(storeKey(gameId));
  } catch {
    /* storage unavailable */
  }
}

export async function join(gameId: string, joinKey: string, label: string, role: string): Promise<Session> {
  let camId: string | undefined;
  try {
    camId = localStorage.getItem(camKey(gameId)) ?? undefined;
  } catch {
    /* storage unavailable */
  }
  const r = await req<{
    cam_id: string;
    cam_token: string;
    exp_ms: number;
    t0_ms: number;
    stdb: { uri: string; module: string };
    frame: Session["frame"];
  }>(`/games/${gameId}/join`, {
    method: "POST",
    body: JSON.stringify({
      join_key: joinKey,
      label,
      role,
      cam_id: camId,
      device: { ua: navigator.userAgent.slice(0, 180), w: screen.width, h: screen.height },
    }),
  });
  const s: Session = {
    gameId,
    camId: r.cam_id,
    token: r.cam_token,
    expMs: r.exp_ms,
    role,
    t0Ms: r.t0_ms,
    // on a local dev origin, reach Spacetime through the dev server's /stdb proxy instead of the public domain
    stdb: /^(127\.0\.0\.1|localhost)$/.test(location.hostname)
      ? { ...r.stdb, uri: `ws://${location.host}/stdb` }
      : r.stdb,
    frame: r.frame,
  };
  try {
    localStorage.setItem(camKey(gameId), r.cam_id);
    localStorage.setItem(storeKey(gameId), JSON.stringify(s));
  } catch {
    /* storage unavailable: the session lasts for this page only */
  }
  return s;
}

export class Api {
  constructor(readonly s: Session) {}

  ctl(cmd: string, args: Record<string, unknown> = {}): Promise<{ req_id: string }> {
    return req("/ctl", { method: "POST", body: JSON.stringify({ cmd, args }) }, this.s.token);
  }
  ask(question: string): Promise<AskAnswer> {
    return req("/ask", { method: "POST", body: JSON.stringify({ question }) }, this.s.token);
  }
  voiceToken(): Promise<VoiceToken> {
    return req("/voice/token", {}, this.s.token);
  }
  async still(): Promise<{ blob: Blob; seq: number; w: number; h: number }> {
    const res = await fetch(`/api/cams/${this.s.camId}/still`, {
      headers: { Authorization: `Bearer ${this.s.token}` },
    });
    if (!res.ok) throw new ApiError(res.status, res.status === 404 ? "no frames yet" : res.statusText);
    return {
      blob: await res.blob(),
      seq: Number(res.headers.get("X-Seq")),
      w: Number(res.headers.get("X-W")),
      h: Number(res.headers.get("X-H")),
    };
  }
  calibrate(r: CalibrationRequest): Promise<Calibration> {
    return req("/calibrate", { method: "POST", body: JSON.stringify(r) }, this.s.token);
  }
  saveCalibration(c: Calibration): Promise<{ ok: boolean; trusted: boolean }> {
    return req(`/cams/${this.s.camId}/calibration`, { method: "POST", body: JSON.stringify(c) }, this.s.token);
  }
  wsUrl(path: "frames" | "ctl"): string {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    return `${proto}://${location.host}/api/ws/${path}?token=${encodeURIComponent(this.s.token)}`;
  }
}
