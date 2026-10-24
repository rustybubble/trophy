// One shared AudioContext, created and resumed inside the Join tap (iOS needs a user gesture).
import onsetWorkletUrl from "./onset.worklet.ts?worker&url";
import { phoneMs } from "./frame.ts";

let ctx: AudioContext | undefined;

const loaded = new Map<string, Promise<void>>();

/** addModule rejects when a processor name is registered twice, so load each worklet once. */
export function ensureWorklet(url: string): Promise<void> {
  if (!loaded.has(url)) loaded.set(url, audioContext().audioWorklet.addModule(url));
  return loaded.get(url)!;
}

export function audioContext(): AudioContext {
  if (!ctx) ctx = new AudioContext({ latencyHint: "interactive" });
  if (ctx.state !== "running") void ctx.resume();
  return ctx;
}

/** Call cues (interfaces-v1 §10 `cue.beep`). */
export function beep(kind: "short" | "double" | "long" | "none"): void {
  if (kind === "none") return;
  const ac = audioContext();
  const tones = kind === "double" ? [0, 0.18] : [0];
  const dur = kind === "long" ? 0.6 : 0.12;
  for (const at of tones) {
    const o = ac.createOscillator();
    const g = ac.createGain();
    o.frequency.value = 1760;
    const t = ac.currentTime + at;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.4, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(ac.destination);
    o.start(t);
    o.stop(t + dur + 0.02);
  }
}

/**
 * Onset detection on a raw mic track (echo cancellation, noise suppression and AGC OFF, to keep the transients).
 * Calls `onOnset` with the phone-clock time of each onset (build card 2D: context time -> performance time).
 */
export async function startOnsets(onOnset: (tPhoneMs: number, peak: number, energy: number) => void): Promise<() => void> {
  const ac = audioContext();
  const mic = await microphone(true);
  await ensureWorklet(onsetWorkletUrl);
  const src = ac.createMediaStreamSource(mic);
  const hp = ac.createBiquadFilter();
  hp.type = "highpass";
  hp.frequency.value = 1500; // ball / racket / clap transients, not voices
  const node = new AudioWorkletNode(ac, "trophy-onset");
  const mute = ac.createGain();
  mute.gain.value = 0;
  src.connect(hp).connect(node).connect(mute).connect(ac.destination); // keep the graph pulled
  node.port.onmessage = (e: MessageEvent<{ tc: number; peak: number; energy: number }>) => {
    const { contextTime, performanceTime } = ac.getOutputTimestamp();
    if (contextTime === undefined || performanceTime === undefined) return;
    onOnset(phoneMs(performanceTime + (e.data.tc - contextTime) * 1000), e.data.peak, e.data.energy);
  };
  return () => {
    node.disconnect();
    src.disconnect();
  };
}

let micStream: MediaStream | undefined;

/**
 * One microphone per page. iOS can mute an earlier capture when a second one starts, so push-to-talk reuses the
 * raw onset mic when it's already open (Ink-2 copes without echo cancellation) instead of opening an
 * echo-cancelled second track (a deviation from interfaces-v1 §16). Pages without onsets open it with EC on.
 */
export async function microphone(raw: boolean): Promise<MediaStream> {
  if (micStream?.getAudioTracks().some((t) => t.readyState === "live")) return micStream;
  micStream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: !raw, noiseSuppression: !raw, autoGainControl: !raw, channelCount: 1 },
  });
  return micStream;
}
