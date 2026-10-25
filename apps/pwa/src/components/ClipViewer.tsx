import { useEffect, useMemo, useRef, useState } from "react";
import type { Call, Camera } from "@trophy/state-client";
import type { Api, ClipMeta } from "../lib/api.ts";

/**
 * Challenge replay, per camera, at 1×, ½× or ¼× with frame steps. Two sources:
 *  - the high-quality segments a camera phone records locally and uploads around the call (D-27), when they arrive;
 *  - until then (or when no phone recorded one, e.g. recorded clips streamed as cameras), the referee's own 720p
 *    recording of the same window, cut by the gateway from the recorder's archive.
 */
export function ClipViewer({
  api,
  call,
  cameras,
  onClose,
}: {
  api: Api;
  call: Call;
  cameras: Camera[];
  onClose: () => void;
}) {
  const [clips, setClips] = useState<ClipMeta[]>([]);
  const [recorded, setRecorded] = useState<Record<string, string>>({}); // cam_id -> blob url of the referee's clip
  const [cam, setCam] = useState<string>();
  const [i, setI] = useState(0);
  const [rate, setRate] = useState(0.5);
  const [waitedS, setWaitedS] = useState(0);
  const video = useRef<HTMLVideoElement>(null);
  const ev = call.evidence[0];
  const startS = (ev?.t0_s ?? call.t_game_s - 2) - 1;
  // the referee's recording: the evidence window ± 1 s, else the 3 s before the call and 1 s after
  const win = useMemo(() => {
    const evs = call.evidence ?? [];
    const t0 = Math.max(0, (evs.length ? Math.min(...evs.map((e) => e.t0_s)) : call.t_game_s - 3) - 1);
    const t1 = (evs.length ? Math.max(...evs.map((e) => e.t1_s)) : call.t_game_s) + 1;
    return { t0, t1: Math.min(t1, t0 + 30) };
  }, [call]);
  const camPhones = useMemo(() => cameras.filter((c) => c.role.split(",").includes("cam")), [cameras]);

  // phone clips: poll for 30 s (they upload a few seconds after the challenge opens)
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

  // the referee's recording of every camera: the recorder finalizes 2 s segments, so a window that ends at the call
  // can take a few seconds to become cuttable
  useEffect(() => {
    let stop = false;
    const urls: string[] = [];
    const t0 = Date.now();
    for (const c of camPhones) {
      void (async () => {
        while (!stop && Date.now() - t0 < 30_000) {
          try {
            const res = await fetch(api.replayClipSrc(c.cam_id, win.t0, win.t1));
            if (res.ok) {
              const url = URL.createObjectURL(await res.blob());
              urls.push(url);
              if (!stop) setRecorded((r) => ({ ...r, [c.cam_id]: url }));
              return;
            }
          } catch {
            /* retry */
          }
          await new Promise((r) => setTimeout(r, 1500));
        }
      })();
    }
    return () => {
      stop = true;
      urls.forEach((u) => URL.revokeObjectURL(u));
    };
  }, [api, camPhones, win.t0, win.t1]);

  const phoneCams = useMemo(() => [...new Set(clips.map((c) => c.cam_id))], [clips]);
  const cams = useMemo(() => [...new Set([...phoneCams, ...camPhones.map((c) => c.cam_id)])], [phoneCams, camPhones]);
  const active = cam ?? cams[0];
  const segs = clips.filter((c) => c.cam_id === active);
  const seg = segs[i];
  const src = seg ? api.clipSrc(seg) : active ? recorded[active] : undefined;
  const fromPhone = !!seg;

  // start at the evidence window (1 s before) in the first segment
  useEffect(() => {
    const v = video.current;
    if (!v || !src) return;
    const onMeta = () => {
      if (seg && i === 0) v.currentTime = Math.max(0, startS - seg.t_game_start_s);
      v.playbackRate = rate;
      void v.play().catch(() => {});
    };
    v.addEventListener("loadedmetadata", onMeta, { once: true });
    return () => v.removeEventListener("loadedmetadata", onMeta);
  }, [src, i, startS, rate, seg]);

  useEffect(() => {
    if (video.current) video.current.playbackRate = rate;
  }, [rate]);

  const step = (dir: number) => {
    const v = video.current;
    if (!v) return;
    v.pause();
    v.currentTime = Math.max(0, v.currentTime + dir / 30);
  };
  const label = (id: string) => camPhones.find((c) => c.cam_id === id)?.label || id;

  return (
    <div className="modal replay">
      <p className="prompt">
        Replay: {call.text}
        <span className="muted small">
          {" "}
          · {fromPhone ? `phone-recorded${seg?.h ? ` ${seg.h}p` : ""}` : "the referee's recording, 720p"}
        </span>
      </p>
      {src ? (
        <video
          ref={video}
          key={src}
          src={src}
          playsInline
          muted
          loop={!fromPhone}
          controls={false}
          onEnded={() => fromPhone && i + 1 < segs.length && setI(i + 1)}
        />
      ) : (
        <p className="muted">
          {waitedS < 30
            ? `Waiting for the replay… ${waitedS}s (phone clips upload, and the referee's recording is cut, a few seconds after the call)`
            : "No replay arrived: no phone uploaded a clip and the referee's recording has no frames for this window."}
        </p>
      )}
      <div className="row">
        {cams.length > 1 &&
          cams.map((c) => (
            <button key={c} className={c === active ? "primary" : ""} onClick={() => (setCam(c), setI(0))}>
              {label(c)}
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
