import { useEffect, useRef, useState } from "react";
import type { Calibration, CalibrationRequest } from "@trophy/contracts";
import type { Api } from "../lib/api.ts";
import { apply, invert3, TABLE_TENNIS } from "../lib/homography.ts";

/** Calibration taps (interfaces-v1 §6): tap the table corners on a still, team A's end first; drag to adjust. */
export function CalibrateView({ api, sport, onClose }: { api: Api; sport: string; onClose: () => void }) {
  const [still, setStill] = useState<{ url: string; seq: number; w: number; h: number }>();
  const [pts, setPts] = useState<[number, number][]>([]);
  const [result, setResult] = useState<Calibration>();
  const [err, setErr] = useState<string>();
  const [busy, setBusy] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);
  const drag = useRef<number | null>(null);
  const landmarks = TABLE_TENNIS;

  useEffect(() => {
    let url: string | undefined;
    api
      .still()
      .then((s) => {
        url = URL.createObjectURL(s.blob);
        setStill({ url, seq: s.seq, w: s.w, h: s.h });
      })
      .catch((e: unknown) => setErr(e instanceof Error ? e.message : String(e)));
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [api]);

  if (sport !== "table_tennis") {
    return (
      <div className="modal">
        <p>Calibration taps for {sport} aren't built yet.</p>
        <button onClick={onClose}>Close</button>
      </div>
    );
  }

  const toImg = (e: React.PointerEvent): [number, number] => {
    const r = imgRef.current!.getBoundingClientRect();
    return [((e.clientX - r.left) / r.width) * still!.w, ((e.clientY - r.top) / r.height) * still!.h];
  };
  const near = (p: [number, number]) => {
    const r = imgRef.current!.getBoundingClientRect();
    const tol = (30 / r.width) * still!.w;
    return pts.findIndex((q) => Math.hypot(q[0] - p[0], q[1] - p[1]) < tol);
  };
  const down = (e: React.PointerEvent) => {
    if (!still) return;
    const p = toImg(e);
    const i = near(p);
    if (i >= 0) {
      drag.current = i;
      (e.target as Element).setPointerCapture(e.pointerId);
    } else if (pts.length < landmarks.length) {
      setPts([...pts, p]);
      setResult(undefined);
    }
  };
  const move = (e: React.PointerEvent) => {
    if (drag.current === null) return;
    const p = toImg(e);
    setPts((old) => old.map((q, i) => (i === drag.current ? p : q)));
    setResult(undefined);
  };

  const solve = async () => {
    if (!still) return;
    setBusy(true);
    setErr(undefined);
    try {
      const r = await api.calibrate({
        schema: "trophy.calibration_request.v1",
        game_id: api.s.gameId,
        cam_id: api.s.camId,
        sport,
        seq: still.seq,
        image_size: { w: still.w, h: still.h },
        points: pts.map((px, i) => ({ name: landmarks[i]!.name, px })) as CalibrationRequest["points"],
      });
      setResult(r);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    if (!result) return;
    setBusy(true);
    try {
      await api.saveCalibration(result);
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  // the solved table outline, projected back into the image
  let outline: string | undefined;
  if (result) {
    try {
      const inv = invert3(result.H_img_to_field);
      outline = landmarks.map((l) => apply(inv, l.pos[0], l.pos[1]).join(",")).join(" ");
    } catch {
      outline = undefined;
    }
  }
  const next = landmarks[pts.length];

  return (
    <div className="modal calibrate">
      <p className="prompt">{next ? `Tap ${pts.length + 1}/4: ${next.prompt}` : result ? "Check the outline, then confirm." : "Drag to adjust, then solve."}</p>
      {still ? (
        <div className="still" onPointerDown={down} onPointerMove={move} onPointerUp={() => (drag.current = null)}>
          <img ref={imgRef} src={still.url} alt="Camera still" draggable={false} />
          <svg viewBox={`0 0 ${still.w} ${still.h}`} preserveAspectRatio="none">
            {outline && <polygon points={outline} className="outline" />}
            {pts.map((p, i) => (
              <g key={i}>
                <circle cx={p[0]} cy={p[1]} r={still.w / 90} className="tap" />
                <text x={p[0] + still.w / 70} y={p[1] - still.w / 70} className="tap-label">
                  {landmarks[i]!.name}
                </text>
              </g>
            ))}
          </svg>
        </div>
      ) : (
        <p className="muted">{err ?? "Loading the latest frame…"}</p>
      )}
      {result && (
        <p className={result.trusted ? "ok" : "warn"}>
          {result.trusted ? "Trusted" : "Not trusted: calls stay BETA"} · reprojection error {result.reproj_err_px.toFixed(1)} px
          {result.warnings.length > 0 && ` · ${result.warnings.join("; ")}`}
        </p>
      )}
      {err && still && <p className="error">{err}</p>}
      <div className="row">
        <button onClick={() => (setPts([]), setResult(undefined))}>Reset</button>
        {!result ? (
          <button className="primary" disabled={pts.length < 4 || busy} onClick={() => void solve()}>
            Solve
          </button>
        ) : (
          <button className="primary" disabled={busy} onClick={() => void confirm()}>
            Confirm
          </button>
        )}
        <button className="ghost" onClick={onClose}>
          Cancel
        </button>
      </div>
    </div>
  );
}
