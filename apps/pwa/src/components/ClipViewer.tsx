import { useEffect, useMemo, useRef, useState } from "react";
import type { Call } from "@trophy/state-client";
import type { Api, ClipMeta } from "../lib/api.ts";

/**
 * High-quality challenge replay: plays the phone-recorded segments around the call's evidence window,
 * per camera, at 1×, ½× or ¼×, with frame steps. Clips arrive a few seconds after the challenge opens.
 */
export function ClipViewer({ api, call, onClose }: { api: Api; call: Call; onClose: () => void }) {
  const [clips, setClips] = useState<ClipMeta[]>([]);
  const [cam, setCam] = useState<string>();
  const [i, setI] = useState(0);
  const [rate, setRate] = useState(0.5);
  const [waitedS, setWaitedS] = useState(0);
  const video = useRef<HTMLVideoElement>(null);
  const ev = call.evidence[0];
  const startS = (ev?.t0_s ?? call.t_game_s - 2) - 1;

  useEffect(() => {
    let stop = false;
    const t0 = Date.now();
    const poll = async () => {
      try {
        const r = await api.listClips(call.id);
        if (!stop) setClips(r.clips);
      } catch {
        /* not there yet */
      }
      if (!stop && Date.now() - t0 < 30_000) setTimeout(() => void poll(), 1500);
      if (!stop) setWaitedS(Math.round((Date.now() - t0) / 1000));
    };
    void poll();
    return () => {
      stop = true;
    };
  }, [api, call.id]);

  const cams = useMemo(() => [...new Set(clips.map((c) => c.cam_id))], [clips]);
  const active = cam ?? cams[0];
  const segs = clips.filter((c) => c.cam_id === active);
  const seg = segs[i];

  // start at the evidence window (1 s before) in the first segment
  useEffect(() => {
    const v = video.current;
    if (!v || !seg) return;
    const onMeta = () => {
      if (i === 0) v.currentTime = Math.max(0, startS - seg.t_game_start_s);
      v.playbackRate = rate;
      void v.play().catch(() => {});
    };
    v.addEventListener("loadedmetadata", onMeta, { once: true });
    return () => v.removeEventListener("loadedmetadata", onMeta);
  }, [seg?.url, i, startS, rate, seg]);

  useEffect(() => {
    if (video.current) video.current.playbackRate = rate;
  }, [rate]);

  const step = (dir: number) => {
    const v = video.current;
    if (!v) return;
    v.pause();
    v.currentTime = Math.max(0, v.currentTime + dir / 30);
  };

  return (
    <div className="modal replay">
      <p className="prompt">
        Replay: {call.text}
        <span className="muted small"> · phone-recorded{seg?.h ? ` ${seg.h}p` : ""}</span>
      </p>
      {seg ? (
        <video
          ref={video}
          key={seg.url}
          src={api.clipSrc(seg)}
          playsInline
          muted
          controls={false}
          onEnded={() => i + 1 < segs.length && setI(i + 1)}
        />
      ) : (
        <p className="muted">
          {waitedS < 30
            ? `Waiting for the cameras to upload their high-quality clips… ${waitedS}s`
            : "No clips arrived."}
        </p>
      )}
      <div className="row">
        {cams.length > 1 &&
          cams.map((c) => (
            <button key={c} className={c === active ? "primary" : ""} onClick={() => (setCam(c), setI(0))}>
              {c}
            </button>
          ))}
        {[1, 0.5, 0.25].map((r) => (
          <button key={r} className={r === rate ? "primary" : ""} onClick={() => setRate(r)}>
            {r === 1 ? "1×" : r === 0.5 ? "½×" : "¼×"}
          </button>
        ))}
        <button onClick={() => step(-1)} aria-label="Previous frame">
          ◀︎ frame
        </button>
        <button onClick={() => step(1)} aria-label="Next frame">
          frame ▶︎
        </button>
        <button onClick={() => video.current?.play()}>Play</button>
        <button className="ghost" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  );
}
