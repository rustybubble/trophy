import { useState } from "react";
import type { MockScript } from "@trophy/state-client";
import demo from "@trophy/state-client/fixtures/table-tennis-demo.json";
import { join, savedSession, type Session } from "../lib/api.ts";
import { audioContext } from "../lib/audio.ts";
import { JoinView } from "../components/JoinView.tsx";
import { LiveView } from "../components/LiveView.tsx";
import "../styles.css";

const params = new URLSearchParams(location.search);
const GAME_RE = /^g_[0-9a-hjkmnp-tv-z]{8}$/;

/**
 * The original live-capture app (phones film the game), kept for `?mode=camera`. The judging demo (D-42) replays
 * recordings instead; see ../ui/JudgeApp.tsx.
 */
export default function LegacyApp() {
  const gameId = params.get("g") ?? "";
  const joinKey = params.get("k") ?? "";
  const mock = params.get("mock") === "1";
  const [session, setSession] = useState<Session | undefined>(() =>
    GAME_RE.test(gameId) ? savedSession(gameId) : undefined,
  );
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  if (mock) {
    // UI development without a backend: plays the labelled-synthetic demo script.
    const fake: Session = {
      gameId: "g_demtt001",
      camId: "c_demca1",
      token: "",
      expMs: Date.now() + 3600_000,
      role: params.get("role") ?? "display,judge",
      t0Ms: Date.now(),
      stdb: { uri: "", module: "" },
      frame: { w: 1280, h: 720, fps: 30, quality: 0.7 },
    };
    return <LiveView session={fake} mock={demo as unknown as MockScript} />;
  }

  if (!GAME_RE.test(gameId)) {
    return (
      <main className="center">
        <h1>Trophy</h1>
        <p>Scan the QR code on the dashboard to join a game.</p>
        <p className="muted">
          Or open <a href="?mode=camera&mock=1">the synthetic demo</a>.
        </p>
      </main>
    );
  }

  if (session) return <LiveView session={session} onLeave={() => setSession(undefined)} />;

  const onJoin = async (label: string, role: string) => {
    setBusy(true);
    setError(undefined);
    audioContext(); // unlock audio inside the tap (iOS)
    try {
      setSession(await join(gameId, joinKey, label, role));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return <JoinView gameId={gameId} hasKey={!!joinKey} busy={busy} error={error} onJoin={onJoin} />;
}
