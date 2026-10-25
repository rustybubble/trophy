import { useRef, useState } from "react";
import type { Moment } from "@trophy/state-client";
import { spriteUrl, type ManifestCam } from "../lib/api.ts";
import { notchKind, spriteCell } from "../lib/moments.ts";
import { fmtDuration } from "../lib/format.ts";

/** The timeline: moment notches (tall = points, short = faults/edges, diamond = bookmarks), a playhead, and a
 *  storyboard-sprite preview on hover when there's a recording. */
export function SeekBar({
  start,
  end,
  now,
  moments,
  cam,
  onSeek,
}: {
  start: number;
  end: number;
  now: number;
  moments: Moment[];
  cam?: ManifestCam;
  onSeek: (t: number) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ t: number; x: number }>();
  const span = Math.max(end - start, 0.001);
  const pct = (t: number) => `${Math.min(100, Math.max(0, ((t - start) / span) * 100))}%`;
  const timeAt = (clientX: number) => {
    const r = ref.current!.getBoundingClientRect();
    return start + Math.min(1, Math.max(0, (clientX - r.left) / r.width)) * span;
  };
  const near = hover && moments.find((m) => Math.abs(m.t_game_s - hover.t) < span * 0.015);
  const cell = hover && cam ? spriteCell(cam.sprite, hover.t - cam.t0_game_s) : undefined;
  return (
    <div className="seek">
      <div
        ref={ref}
        className="track"
        role="slider"
        aria-label="Seek"
        aria-valuemin={start}
        aria-valuemax={end}
        aria-valuenow={now}
        tabIndex={0}
        onPointerMove={(e) =>
          setHover({ t: timeAt(e.clientX), x: e.clientX - ref.current!.getBoundingClientRect().left })
        }
        onPointerLeave={() => setHover(undefined)}
        onPointerDown={(e) => {
          (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
          onSeek(timeAt(e.clientX));
        }}
      >
        <div className="played" style={{ width: pct(now) }} />
        {moments.map((m) => (
          <span
            key={m.moment_id}
            className={`notch ${notchKind(m)}${m.is_best_play ? " best" : ""}`}
            style={{ left: pct(m.t_game_s) }}
            title={m.label}
          />
        ))}
        <span className="head" style={{ left: pct(now) }} />
        {hover && (
          <div className="preview" style={{ left: Math.max(0, hover.x - 80) }}>
            {cell && cam && (
              <div
                className="sprite"
                style={{
                  backgroundImage: `url(${spriteUrl(cam, cell.sheet)})`,
                  backgroundPosition: `-${cell.x}px -${cell.y}px`,
                  width: cam.sprite.w,
                  height: cam.sprite.h,
                }}
              />
            )}
            <div className="small">
              {fmtDuration(hover.t - start)}
              {near ? ` · ${near.label}` : ""}
            </div>
          </div>
        )}
      </div>
      <div className="times small muted">
        <span>{fmtDuration(now - start)}</span>
        <span>{fmtDuration(end - start)}</span>
      </div>
    </div>
  );
}
