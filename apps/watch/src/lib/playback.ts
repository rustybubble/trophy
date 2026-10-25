// One transport for both cases: a recording (HLS in a <video>, game time = media time + the camera's t0) or no
// recording yet (a virtual clock over the game's time range, e.g. the synthetic demo). Overlays read time from the
// vendored tv-core clock, never from a bare timer.
import Hls from "hls.js";
import { createClock, type Clock, type MediaClockSource } from "../vendor/tv-core/clock.ts";

export interface Transport extends MediaClockSource {
  /** Game time now (seconds). */
  gameTime(): number;
  seekGame(t: number): void;
  play(): void;
  pause(): void;
  setRate(r: number): void;
  rate(): number;
  /** Step one frame (1/30 s) while paused. */
  step(dir: 1 | -1): void;
  destroy(): void;
  readonly hasVideo: boolean;
  readonly start: number;
  readonly end: number;
}

export class VirtualTransport implements Transport {
  readonly hasVideo = false;
  private base: number;
  private wall = 0;
  private playing = false;
  private r = 1;
  constructor(
    readonly start: number,
    readonly end: number,
  ) {
    this.base = start;
  }
  currentTime(): number {
    if (!this.playing) return this.base;
    const t = this.base + ((performance.now() - this.wall) / 1000) * this.r;
    if (t >= this.end) {
      this.base = this.end;
      this.playing = false;
      return this.end;
    }
    return t;
  }
  paused(): boolean {
    this.currentTime(); // stops at the end
    return !this.playing;
  }
  gameTime(): number {
    return this.currentTime();
  }
  seekGame(t: number): void {
    this.base = Math.min(this.end, Math.max(this.start, t));
    this.wall = performance.now();
  }
  play(): void {
    if (this.base >= this.end) this.base = this.start;
    this.wall = performance.now();
    this.playing = true;
  }
  pause(): void {
    this.base = this.currentTime();
    this.playing = false;
  }
  setRate(r: number): void {
    this.base = this.currentTime();
    this.wall = performance.now();
    this.r = r;
  }
  rate(): number {
    return this.r;
  }
  step(dir: 1 | -1): void {
    this.pause();
    this.seekGame(this.base + dir / 30);
  }
  destroy(): void {}
}

export class VideoTransport implements Transport {
  readonly hasVideo = true;
  private hls: Hls | undefined;
  constructor(
    private readonly video: HTMLVideoElement,
    src: string,
    /** game time of media time 0 (the camera's t0_game_s) */
    private readonly t0: number,
    duration: number,
  ) {
    this.start = t0;
    this.end = t0 + duration;
    // hls.js wherever MediaSource exists (some Chromium builds answer "maybe" to native HLS and then can't play it);
    // native HLS only as the fallback (older iOS Safari without MSE)
    if (Hls.isSupported()) {
      this.hls = new Hls({ maxBufferLength: 20 });
      this.hls.loadSource(src);
      this.hls.attachMedia(video);
    } else {
      video.src = src;
    }
  }
  readonly start: number;
  readonly end: number;
  currentTime(): number {
    return this.video.currentTime;
  }
  paused(): boolean {
    return this.video.paused;
  }
  gameTime(): number {
    return this.video.currentTime + this.t0;
  }
  seekGame(t: number): void {
    this.video.currentTime = Math.max(0, t - this.t0);
  }
  play(): void {
    void this.video.play().catch(() => undefined);
  }
  pause(): void {
    this.video.pause();
  }
  setRate(r: number): void {
    this.video.playbackRate = r;
  }
  rate(): number {
    return this.video.playbackRate;
  }
  step(dir: 1 | -1): void {
    this.video.pause();
    this.video.currentTime = Math.max(0, this.video.currentTime + dir / 30);
  }
  destroy(): void {
    this.hls?.destroy();
  }
}

/** A clock in game time over either transport. */
export function gameClock(t: Transport): Clock {
  const offset = t.hasVideo ? t.gameTime() - t.currentTime() : 0;
  const media = createClock(t);
  return {
    now: () => media.now() + offset,
    subscribe: (fn) => media.subscribe((m) => fn(m + offset)),
    stop: () => media.stop(),
  };
}
