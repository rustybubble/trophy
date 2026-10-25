import { useEffect, useState } from "react";
import type { Feed } from "@trophy/state-client";
import { ApiError, type Scenario } from "../lib/api.ts";
import type { Backend } from "../lib/backend.ts";
import { Sheet } from "./Sheet.tsx";

const SOURCE_TEXT: Record<Scenario["source"], string> = {
  team_recording: "our recording",
  cc_by_online: "CC BY clip",
  synthetic: "synthetic",
};

/** Host controls (any judge phone): pick a recorded scenario, Go live, Stop. Plus sound and leaving. */
export function GameSheet(props: {
  backend: Backend;
  feeds: Feed[];
  gameId: string;
  joinLink?: string;
  soundOn: boolean;
  onSound: (on: boolean) => void;
  onLeave?: () => void;
  say: (m: string) => void;
  onClose: () => void;
}) {
  const { backend, say } = props;
  const [list, setList] = useState<Scenario[]>();
  const [err, setErr] = useState<string>();
  const live = props.feeds.find((f) => f.status === "scheduled" || f.status === "playing");
  const [pick, setPick] = useState<string>();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let off = false;
    backend.scenarios().then(
      (s) => !off && setList(s),
      (e: unknown) => !off && setErr(e instanceof Error ? e.message : String(e)),
    );
    return () => {
      off = true;
    };
  }, [backend]);

  const chosen = pick ?? live?.scenario_id ?? list?.[0]?.id;

  const go = async () => {
    if (!chosen) return;
    setBusy(true);
    try {
      await backend.goLive(chosen);
      say("Going live: every phone starts in a few seconds");
      props.onClose();
    } catch (e) {
      say(
        e instanceof ApiError && e.status === 409
          ? "A scenario is already playing. Stop it first."
          : `Go live failed: ${e instanceof Error ? e.message : String(e)}`,
      );
    } finally {
      setBusy(false);
    }
  };
  const stop = async () => {
    setBusy(true);
    try {
      await backend.stop();
      say("Stopped");
    } catch (e) {
      say(`Stop failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  };
  const share = async () => {
    if (!props.joinLink) return;
    try {
      if (navigator.share) await navigator.share({ title: "Join Trophy", url: props.joinLink });
      else {
        await navigator.clipboard.writeText(props.joinLink);
        say("Join link copied");
      }
    } catch {
      /* share sheet dismissed */
    }
  };

  return (
    <Sheet title="Game" onClose={props.onClose}>
      <section className="section">
        <h3>Scenario</h3>
        {err && <p className="small err">Couldn't load scenarios: {err}</p>}
        {!list && !err && <p className="small muted">Loading…</p>}
        <div className="scenarios" role="radiogroup" aria-label="Scenario">
          {list?.map((s) => (
            <button
              key={s.id}
              role="radio"
              aria-checked={s.id === chosen}
              className={s.id === chosen ? "scenario on" : "scenario"}
              onClick={() => setPick(s.id)}
            >
              <b>{s.title}</b>
              <span>
                {s.angles.length} angle{s.angles.length === 1 ? "" : "s"} · {SOURCE_TEXT[s.source]}
                {s.annotated ? " · annotated" : ""}
                {s.ready === false ? " · not prepared yet" : ""}
              </span>
            </button>
          ))}
        </div>
        {live ? (
          <>
            <p className="small muted">
              Live now: {list?.find((s) => s.id === live.scenario_id)?.title ?? live.scenario_id} ({live.status})
            </p>
            <div className="run-actions">
              <button className="btn danger" disabled={busy} onClick={() => void stop()}>
                Stop
              </button>
            </div>
          </>
        ) : (
          <button className="btn primary big block" disabled={busy || !chosen} onClick={() => void go()}>
            {busy ? "Starting…" : "Go live"}
          </button>
        )}
        <p className="fine">The laptop replays the recording as if live; each phone shows one angle in sync.</p>
      </section>

      <section className="section">
        <h3>Phone</h3>
        <label className="switch">
          Sound (beeps and spoken calls)
          <input type="checkbox" checked={props.soundOn} onChange={(e) => props.onSound(e.target.checked)} />
        </label>
        {props.joinLink && (
          <button className="btn block" onClick={() => void share()}>
            Invite another phone
          </button>
        )}
        {props.onLeave && (
          <button className="btn block" onClick={props.onLeave}>
            Leave game
          </button>
        )}
        <p className="fine mono">{props.gameId}</p>
      </section>
    </Sheet>
  );
}
