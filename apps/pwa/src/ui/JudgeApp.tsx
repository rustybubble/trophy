import { useEffect, useState } from "react";
import { createGame, join, savedSession, type Session } from "../lib/api.ts";
import { audioContext } from "../lib/audio.ts";
import { MOCK_GAME, MockBackend } from "../mock/mockBackend.ts";
import { TrophyIcon } from "./icons.tsx";
import { Main } from "./Main.tsx";
import "./app.css";

const params = new URLSearchParams(location.search);
const GAME_RE = /^g_[0-9a-hjkmnp-tv-z]{8}$/;
const ROLE = "display,judge"; // every phone can challenge, add house rules and run scenarios (no role picker)
const MOCK_CAM = "c_mockme01";

const loadName = () => {
  try {
    return localStorage.getItem("trophy.name") ?? "";
  } catch {
    return "";
  }
};
const saveName = (n: string) => {
  try {
    localStorage.setItem("trophy.name", n);
  } catch {
    /* storage unavailable */
  }
};

function Landing() {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string>();
  const start = async () => {
    setBusy(true);
    setErr(undefined);
    try {
      const g = await createGame("table_tennis");
      location.assign(`?g=${encodeURIComponent(g.game_id)}&k=${encodeURIComponent(g.join_key)}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };
  return (
    <main className="page">
      <div className="brand">
        <TrophyIcon />
        <h1>Trophy</h1>
      </div>
      <p className="lede">Every phone is a camera angle.</p>
      <button className="btn primary big block" disabled={busy} onClick={() => void start()}>
        {busy ? "Creating…" : "Start a new game"}
      </button>
      {err && <p className="err">{err}</p>}
      <p className="fine">
        Joining a game? Scan its QR code with the camera. No laptop nearby? Open the <a href="?mock=1">offline mock</a>{" "}
        (synthetic data).
      </p>
    </main>
  );
}

function Join(props: { gameId: string; mock: boolean; hasKey: boolean; onJoin: (name: string) => Promise<void> }) {
  const [name, setName] = useState(loadName);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string>();
  const ok = name.trim().length > 0 && (props.mock || props.hasKey);
  const go = async () => {
    audioContext(); // unlock audio inside the tap (iOS)
    setBusy(true);
    setErr(undefined);
    try {
      saveName(name.trim());
      await props.onJoin(name.trim());
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };
  return (
    <main className="page">
      <div className="brand">
        <TrophyIcon />
        <h1>Join the game</h1>
      </div>
      <p className="lede">Calls are spoken. Turn your sound up.</p>
      <form
        className="section"
        onSubmit={(e) => {
          e.preventDefault();
          if (ok && !busy) void go();
        }}
      >
        <label className="field">
          Your name
          <input
            value={name}
            maxLength={20}
            autoComplete="nickname"
            autoCapitalize="words"
            enterKeyHint="go"
            placeholder="e.g. Sam"
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <button className="btn primary big block" type="submit" disabled={!ok || busy}>
          {busy ? "Joining…" : "Join"}
        </button>
      </form>
      {!props.mock && !props.hasKey && <p className="err">This link has no join key. Scan the QR code again.</p>}
      {err && <p className="err">{err}</p>}
      <p className="fine mono">{props.mock ? "Offline mock · synthetic data, no backend" : props.gameId}</p>
    </main>
  );
}

export default function JudgeApp() {
  const mock = params.get("mock") === "1";
  const gameId = mock ? MOCK_GAME : (params.get("g") ?? "");
  const joinKey = params.get("k") ?? "";
  const [name, setName] = useState(loadName);
  const [session, setSession] = useState<Session | undefined>(() => {
    if (mock || !GAME_RE.test(gameId)) return undefined;
    const s = savedSession(gameId);
    return s && s.role.split(",").includes("judge") && loadName() ? s : undefined;
  });
  const [mockBackend, setMockBackend] = useState<MockBackend>();
  useEffect(() => () => mockBackend?.dispose(), [mockBackend]);

  if (!mock && !GAME_RE.test(gameId)) return <Landing />;

  if (!session) {
    const onJoin = async (n: string) => {
      setName(n);
      if (mock) {
        setMockBackend(new MockBackend(MOCK_CAM));
        setSession({
          gameId: MOCK_GAME,
          camId: MOCK_CAM,
          token: "",
          expMs: Date.now() + 3600_000,
          role: ROLE,
          t0Ms: Date.now(),
          stdb: { uri: "", module: "" },
          frame: { w: 1280, h: 720, fps: 30, quality: 0.7 },
        });
        return;
      }
      setSession(await join(gameId, joinKey, n, ROLE));
    };
    return <Join gameId={gameId} mock={mock} hasKey={!!joinKey} onJoin={onJoin} />;
  }

  const joinLink =
    !mock && joinKey
      ? `${location.origin}${location.pathname}?g=${encodeURIComponent(gameId)}&k=${encodeURIComponent(joinKey)}`
      : undefined;
  return (
    <Main
      key={session.camId}
      session={session}
      name={name || "Phone"}
      mock={mockBackend}
      joinLink={joinLink}
      onLeave={() => {
        setMockBackend(undefined);
        setSession(undefined);
      }}
    />
  );
}
