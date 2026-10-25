import { useEffect, useRef, useState } from "react";
import type { Feed } from "@trophy/state-client";
import { fmtDrift } from "../lib/demo.ts";
import { clipToGame, correctionFor, phaseAt, targetClipTime } from "../lib/sync.ts";
import type { TrackBuffer } from "../lib/useTrophy.ts";

export interface PlayStatus {
  playing: boolean;
  driftMs: number | null;
}

/** Map a source-pixel point to the element, for a video drawn with object-fit: contain. */
function containPoint(v: HTMLVideoElement, px: [number, number]): [number, number] | undefined {
  const vw = v.videoWidth;
  const vh = v.videoHeight;
  if (!vw || !vh) return undefined;
  const w = v.clientWidth;
  const h = v.clientHeight;
  const s = Math.min(w / vw, h / vh);
  return [(w - vw * s) / 2 + px[0] * s, (h - vh * s) / 2 + px[1] * s];
}

/**
 * The angle this phone hosts, played in sync with the server schedule (D-42): a countdown before wall0_ms, then
 * currentTime = offset_s + (serverNow - wall0_ms)/1000, seeking past 120 ms of drift and nudging playbackRate
 * (0.97-1.03) below that. The ball dot comes from this camera's Spacetime track_sample rows.
 */
export function AngleVideo(props: {
  feed: Feed;
  src: string;
  serverNow: () => number;
  track: TrackBuffer;
  onStatus: (s: PlayStatus) => void;
}) {
  const { feed, src, serverNow, track, onStatus } = props;
  const video = useRef<HTMLVideoElement>(null);
  const dot = useRef<HTMLDivElement>(null);
  const [phase, setPhase] = useState<"countdown" | "playing" | "ended">("countdown");
  const [count, setCount] = useState<number>();
  const [blocked, setBlocked] = useState(false);
  const [error, setError] = useState<string>();
  const [drift, setDrift] = useState<number | null>(null);
  const statusRef = useRef(onStatus);
  statusRef.current = onStatus;
  const nowRef = useRef(serverNow);
  nowRef.current = serverNow;

  // iOS needs the muted *attribute* for inline autoplay (React only sets the property)
  useEffect(() => {
    const v = video.current;
    if (!v) return;
    v.muted = true;
    v.setAttribute("muted", "");
    v.setAttribute("playsinline", "");
    v.setAttribute("webkit-playsinline", "");
  }, []);

  useEffect(() => {
    setError(undefined);
    setBlocked(false);
  }, [src]);

  // the sync loop
  useEffect(() => {
    const v = video.current;
    if (!v) return;
    let lastSeek = 0;
    let lead = 0.05; // seconds; learned from how far behind a seek lands
    let checkAfterSeek = false;
    let lastCount: number | undefined;
    let lastPhase = "";
    const onSeeked = () => {
      checkAfterSeek = true;
    };
    v.addEventListener("seeked", onSeeked);
    const tick = () => {
      const now = nowRef.current();
      const ph = phaseAt(feed, now);
      if (ph.kind !== lastPhase) {
        lastPhase = ph.kind;
        setPhase(ph.kind);
      }
      if (ph.kind === "countdown") {
        if (ph.seconds !== lastCount) setCount((lastCount = ph.seconds));
        if (!v.paused) v.pause();
        if (v.readyState >= 1 && Math.abs(v.currentTime - feed.offset_s) > 0.05 && !v.seeking)
          v.currentTime = feed.offset_s;
        setDrift(null);
        statusRef.current({ playing: false, driftMs: null });
        return;
      }
      if (ph.kind === "ended") {
        if (!v.paused) v.pause();
        setDrift(null);
        statusRef.current({ playing: false, driftMs: null });
        return;
      }
      if (v.readyState < 1) return;
      const target = targetClipTime(feed, now);
      if (v.paused) {
        v.currentTime = target + lead;
        lastSeek = performance.now();
        v.play().then(
          () => setBlocked(false),
          (e: unknown) => {
            if (e instanceof DOMException && e.name === "NotAllowedError") setBlocked(true);
          },
        );
        return;
      }
      if (v.seeking) return;
      const d = (v.currentTime - target) * 1000;
      if (checkAfterSeek && performance.now() - lastSeek > 250) {
        checkAfterSeek = false;
        lead = Math.min(0.5, Math.max(0, lead - d / 1000)); // landed behind -> lead more next time
      }
      setDrift(Math.round(d));
      statusRef.current({ playing: true, driftMs: d });
      const c = correctionFor(d);
      if (c.kind === "seek") {
        if (performance.now() - lastSeek > 800) {
          v.currentTime = target + lead;
          lastSeek = performance.now();
        }
      } else if (Math.abs(v.playbackRate - c.rate) > 0.001) {
        v.playbackRate = c.rate;
      }
    };
    tick();
    const id = setInterval(tick, 200);
    return () => {
      clearInterval(id);
      v.removeEventListener("seeked", onSeeked);
    };
  }, [feed, src]);

  // the ball dot, drawn without React renders
  useEffect(() => {
    let raf = 0;
    const draw = () => {
      raf = requestAnimationFrame(draw);
      const v = video.current;
      const el = dot.current;
      if (!v || !el) return;
      const px = !v.paused ? track.pxAt(feed.cam_id, clipToGame(feed, v.currentTime)) : undefined;
      const at = px && containPoint(v, px);
      if (at) {
        el.style.transform = `translate(${at[0]}px, ${at[1]}px)`;
        el.style.opacity = "1";
      } else el.style.opacity = "0";
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [feed, track]);

  const driftCls =
    drift === null ? "" : Math.abs(drift) < 40 ? "drift-ok" : Math.abs(drift) < 120 ? "drift-warn" : "drift-bad";

  return (
    <div className="stage">
      <video
        ref={video}
        src={src}
        muted
        playsInline
        preload="auto"
        disablePictureInPicture
        onError={() => setError("This angle's video didn't load.")}
      />
      <div ref={dot} className="ball" aria-hidden />
      <span className="angle-tag">{feed.label.toUpperCase()}</span>
      {phase === "playing" && drift !== null && (
        <span className={`drift-tag ${driftCls}`} aria-label="Drift from the shared schedule">
          {fmtDrift(drift)}
        </span>
      )}
      {phase === "countdown" && count !== undefined && (
        <div className="overlay">
          {count <= 3 ? (
            <div>
              <div className="countdown" key={count}>
                {count}
              </div>
            </div>
          ) : (
            <p>Starting in {count} s</p>
          )}
        </div>
      )}
      {phase === "ended" && (
        <div className="overlay">
          <p>This replay has ended.</p>
        </div>
      )}
      {blocked && phase === "playing" && (
        <button className="overlay" onClick={() => void video.current?.play().then(() => setBlocked(false))}>
          <span className="btn primary">Tap to start the video</span>
        </button>
      )}
      {error && (
        <div className="overlay">
          <p className="err">{error}</p>
        </div>
      )}
    </div>
  );
}
