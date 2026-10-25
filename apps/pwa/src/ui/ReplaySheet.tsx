import { useEffect, useMemo, useRef, useState } from "react";
import type { AiVote, Call, Challenge, Feed } from "@trophy/state-client";
import type { Backend } from "../lib/backend.ts";
import { explanationFor, replayWindows, sortFeeds, VERDICT_TEXT, verdictOf, type ClipWindow } from "../lib/demo.ts";
import { gameToClip } from "../lib/sync.ts";
import { tierLabel } from "./parts.tsx";
import { Sheet } from "./Sheet.tsx";

/**
 * One angle of the replay: the recorder clip for the evidence window (GET /api/replay/{g}/clip), or, when there is no
 * recorder clip (mock, not recorded yet, error), the angle's scenario file seeked to the same window. Loops.
 */
function ReplayAngle({ feed, win, backend, rate }: { feed: Feed; win: ClipWindow; backend: Backend; rate: number }) {
  const recorder = backend.clipSrc(win.cam_id, win.t0_s, win.t1_s);
  const [useFile, setUseFile] = useState(!recorder);
  const video = useRef<HTMLVideoElement>(null);
  const start = useFile ? Math.max(0, gameToClip(feed, win.t0_s)) : 0;
  const end = useFile ? gameToClip(feed, win.t1_s) : Infinity;
  const src = useFile ? backend.feedSrc(feed) : recorder!;

  useEffect(() => {
    const v = video.current;
    if (!v) return;
    v.muted = true;
    v.setAttribute("muted", "");
    const onMeta = () => {
      v.currentTime = start;
      v.playbackRate = rate;
      void v.play().catch(() => {});
    };
    const onTime = () => {
      if (v.currentTime >= end) v.currentTime = start;
    };
    const onEnded = () => {
      v.currentTime = start;
      void v.play().catch(() => {});
    };
    v.addEventListener("loadedmetadata", onMeta);
    v.addEventListener("timeupdate", onTime);
    v.addEventListener("ended", onEnded);
    if (v.readyState >= 1) onMeta();
    return () => {
      v.removeEventListener("loadedmetadata", onMeta);
      v.removeEventListener("timeupdate", onTime);
      v.removeEventListener("ended", onEnded);
    };
  }, [src, start, end, rate]);

  useEffect(() => {
    if (video.current) video.current.playbackRate = rate;
  }, [rate]);

  return (
    <div className="replay-video">
      <video
        key={src}
        ref={video}
        src={src}
        muted
        playsInline
        preload="auto"
        onError={() => !useFile && setUseFile(true)}
      />
      <span className="src">
        {useFile ? "scenario file" : "recorder clip"} · {win.t0_s.toFixed(1)}–{win.t1_s.toFixed(1)} s
      </span>
    </div>
  );
}

/** Opens on every phone when a challenge opens: the angles, then the automatic verdict with its explanation. */
export function ReplaySheet(props: {
  challenge: Challenge;
  calls: Call[];
  feeds: Feed[];
  votes: AiVote[];
  backend: Backend;
  onClose: () => void;
}) {
  const { challenge, calls, votes, backend } = props;
  const call = calls.find((c) => c.id === challenge.call_id);
  const feeds = useMemo(() => sortFeeds(props.feeds), [props.feeds]);
  const [cam, setCam] = useState<string>();
  const [rate, setRate] = useState(1);
  const verdict = verdictOf(challenge);
  const { text: explanation, replacement } = explanationFor(challenge, calls);
  const claude = votes.find((v) => v.call_id === challenge.call_id && v.backend === "claude");
  const windows = useMemo(
    () =>
      call
        ? replayWindows(
            call,
            feeds.map((f) => f.cam_id),
          )
        : [],
    [call, feeds],
  );
  const active = feeds.find((f) => f.cam_id === cam) ?? feeds[0];
  const win = windows.find((w) => w.cam_id === active?.cam_id);
  const top = claude?.probs ? Object.entries(claude.probs).sort((a, b) => b[1] - a[1])[0] : undefined;

  return (
    <Sheet title="Replay" onClose={props.onClose} tall>
      {call && (
        <div className="small muted">
          Challenged: <b style={{ color: "var(--fg)" }}>{call.text}</b> · {tierLabel(call)}
          {call.at_fault ? ` · on ${call.at_fault.name}` : ""}
          {call.source === "annotated" ? " · annotated" : ""}
        </div>
      )}
      {feeds.length > 1 && (
        <div className="seg" role="tablist" aria-label="Camera angle">
          {feeds.map((f) => (
            <button
              key={f.cam_id}
              role="tab"
              aria-selected={f.cam_id === active?.cam_id}
              className={f.cam_id === active?.cam_id ? "pill on" : "pill"}
              onClick={() => setCam(f.cam_id)}
            >
              {f.label}
            </button>
          ))}
        </div>
      )}
      {active && win ? (
        <ReplayAngle key={active.cam_id} feed={active} win={win} backend={backend} rate={rate} />
      ) : (
        <div className="replay-video">
          <div className="overlay">
            <p className="muted">No angle to replay.</p>
          </div>
        </div>
      )}
      <div className="seg">
        {[1, 0.5, 0.25].map((r) => (
          <button key={r} className={r === rate ? "pill on" : "pill"} onClick={() => setRate(r)}>
            {r === 1 ? "1×" : r === 0.5 ? "½×" : "¼×"}
          </button>
        ))}
      </div>

      <div className={`verdict ${verdict}`} aria-live="assertive">
        {verdict === "reviewing" ? (
          <div className="note" style={{ color: "var(--fg)", fontSize: 17 }}>
            <span className="spinner" /> Reviewing… geometry and Claude re-check the play
          </div>
        ) : (
          <>
            <div className="v">{VERDICT_TEXT[verdict]}</div>
            {explanation && <p>{explanation}</p>}
            {replacement && (
              <div className="small muted">
                New call: <b style={{ color: "var(--fg)" }}>{replacement.text}</b>
              </div>
            )}
            <div className="small muted">
              {challenge.decided_by === "judge" ? "Decided by the judge" : "Decided automatically"}
              {typeof challenge.p_original === "number"
                ? ` · ${Math.round(challenge.p_original * 100)}% the original call was right (uncalibrated)`
                : ""}
            </div>
          </>
        )}
      </div>

      <div className="card vote">
        <div className="head">
          <span>Claude</span>
          <span className="tag">uncalibrated</span>
        </div>
        {claude ? (
          claude.error ? (
            <span className="small err">Vote failed: {claude.error}</span>
          ) : (
            <>
              {top && (
                <>
                  <div className="small">
                    {(claude.choice ?? top[0]).replace(/_/g, " ").toLowerCase()} · {Math.round(top[1] * 100)}%
                  </div>
                  <div className="bar-meter">
                    <i style={{ width: `${Math.round(top[1] * 100)}%` }} />
                  </div>
                </>
              )}
              {claude.rationale && <div className="small muted">{claude.rationale}</div>}
              <div className="small muted">
                {claude.model} · {(claude.latency_ms / 1000).toFixed(1)} s
              </div>
            </>
          )
        ) : (
          <span className="small muted">{verdict === "reviewing" ? "Voting…" : "No model vote for this call."}</span>
        )}
      </div>
    </Sheet>
  );
}
