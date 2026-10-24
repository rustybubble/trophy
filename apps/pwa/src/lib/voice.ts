// Cartesia voice (interfaces-v1 §16): Sonic TTS over one WebSocket and Ink-2 push-to-talk STT, both with a
// short-lived token from the gateway (the API key never reaches the phone).
import tapWorkletUrl from "./tap.worklet.ts?worker&url";
import type { Api, VoiceToken } from "./api.ts";
import { audioContext, ensureWorklet, microphone } from "./audio.ts";

export type VoiceName = "calls" | "ref";

export class Voice {
  private token: VoiceToken | undefined;
  private tts: WebSocket | undefined;
  private ttsReady: Promise<WebSocket> | undefined;
  private sources = new Map<string, AudioBufferSourceNode[]>();
  private firstAudio = new Map<string, (t: number) => void>();
  private next = 0;
  private current: string | undefined;
  enabled = true;

  constructor(private readonly api: Api) {}

  async tokenFresh(): Promise<VoiceToken> {
    if (!this.token || this.token.expires_at_ms - Date.now() < 30_000) this.token = await this.api.voiceToken();
    return this.token;
  }

  /** Fetch a token and open the TTS socket ahead of the first call (saves ~0.3 s on it). */
  async warm(): Promise<void> {
    await this.socket();
  }

  private socket(): Promise<WebSocket> {
    if (this.tts && this.tts.readyState === WebSocket.OPEN && this.ttsReady) return this.ttsReady;
    this.ttsReady = (async () => {
      const t = await this.tokenFresh();
      const ws = new WebSocket(
        `wss://api.cartesia.ai/tts/websocket?cartesia_version=${t.cartesia_version}&access_token=${encodeURIComponent(t.access_token)}`,
      );
      ws.onmessage = (e) => this.onTts(JSON.parse(String(e.data)) as Record<string, unknown>);
      ws.onclose = () => {
        if (this.tts === ws) this.tts = undefined;
      };
      await new Promise<void>((res, rej) => {
        ws.onopen = () => res();
        ws.onerror = () => rej(new Error("TTS socket failed"));
      });
      this.tts = ws;
      return ws;
    })();
    return this.ttsReady;
  }

  /**
   * Speak a line. `interrupt` cancels the line that's playing (a newer call makes it stale).
   * Resolves with the ms from the request to the first audio being scheduled.
   */
  async speak(text: string, opts: { voice?: VoiceName; emotion?: string; interrupt?: boolean } = {}): Promise<number> {
    if (!this.enabled || !text.trim()) return 0;
    const ac = audioContext();
    if (opts.interrupt && this.current) this.cancel(this.current);
    const ws = await this.socket();
    const t = await this.tokenFresh();
    const id = crypto.randomUUID();
    this.current = id;
    this.sources.set(id, []);
    const t0 = performance.now();
    const first = new Promise<number>((res) => this.firstAudio.set(id, (tt) => res(tt - t0)));
    const transcript = opts.emotion ? `<emotion value="${opts.emotion}"/>${text}` : text;
    ws.send(
      JSON.stringify({
        model_id: "sonic-3.6",
        transcript,
        voice: { mode: "id", id: t.voices[opts.voice ?? "calls"] },
        language: "en",
        context_id: id,
        output_format: { container: "raw", encoding: "pcm_f32le", sample_rate: ac.sampleRate },
        max_buffer_delay_ms: 0,
        continue: false,
      }),
    );
    return first;
  }

  cancel(id: string): void {
    if (this.tts?.readyState === WebSocket.OPEN) this.tts.send(JSON.stringify({ context_id: id, cancel: true }));
    for (const s of this.sources.get(id) ?? []) {
      try {
        s.stop();
      } catch {
        /* already stopped */
      }
    }
    this.sources.delete(id);
    if (this.current === id) this.current = undefined;
    this.next = 0;
  }

  private onTts(m: Record<string, unknown>): void {
    const id = String(m.context_id ?? "");
    if (m.type === "chunk" && typeof m.data === "string" && this.sources.has(id)) {
      const ac = audioContext();
      const bin = atob(m.data);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const f = new Float32Array(bytes.buffer);
      if (!f.length) return;
      const buf = ac.createBuffer(1, f.length, ac.sampleRate);
      buf.copyToChannel(f, 0);
      const src = ac.createBufferSource();
      src.buffer = buf;
      src.connect(ac.destination);
      this.next = Math.max(this.next, ac.currentTime + 0.02);
      src.start(this.next);
      this.next += buf.duration;
      this.sources.get(id)!.push(src);
      const cb = this.firstAudio.get(id);
      if (cb) {
        cb(performance.now());
        this.firstAudio.delete(id);
      }
    }
    if (m.done === true) this.firstAudio.delete(id);
  }

  /** Push-to-talk: call on press; the returned `release()` resolves with the final transcript. */
  async listen(onPartial: (text: string) => void): Promise<{ release: () => Promise<string> }> {
    const ac = audioContext();
    const mic = await microphone(false);
    const t = await this.tokenFresh();
    await ensureWorklet(tapWorkletUrl);
    const node = new AudioWorkletNode(ac, "trophy-tap");
    const src = ac.createMediaStreamSource(mic);
    const mute = ac.createGain();
    mute.gain.value = 0;
    src.connect(node).connect(mute).connect(ac.destination);
    const ws = new WebSocket(
      "wss://api.cartesia.ai/stt/turns/websocket?model=ink-2&encoding=pcm_s16le&sample_rate=16000" +
        `&cartesia_version=${t.cartesia_version}&access_token=${encodeURIComponent(t.access_token)}`,
    );
    ws.binaryType = "arraybuffer";
    const turns: string[] = [];
    let partial = "";
    let releasedAt = 0;
    const done = new Promise<string>((resolve) => {
      ws.onmessage = (e) => {
        const m = JSON.parse(String(e.data)) as { type: string; transcript?: string };
        if (m.type === "turn.update" || m.type === "turn.eager_end") {
          partial = m.transcript ?? "";
          onPartial([...turns, partial].join(" ").trim());
        } else if (m.type === "turn.end") {
          turns.push(m.transcript ?? "");
          partial = "";
          onPartial(turns.join(" ").trim());
        }
      };
      ws.onclose = () => resolve([...turns, partial].join(" ").trim());
    });

    // naive decimation to 16 kHz, 100 ms chunks
    const ratio = ac.sampleRate / 16000;
    let carry = new Float32Array(0);
    let pending: Int16Array[] = [];
    let pendingLen = 0;
    node.port.onmessage = (e: MessageEvent<Float32Array>) => {
      if (ws.readyState > WebSocket.OPEN || (releasedAt && performance.now() - releasedAt > 1200)) return;
      const all = new Float32Array(carry.length + e.data.length);
      all.set(carry);
      all.set(e.data, carry.length);
      const n = Math.floor(all.length / ratio);
      const out = new Int16Array(n);
      for (let i = 0; i < n; i++) {
        const s = Math.max(-1, Math.min(1, all[Math.floor(i * ratio)]!));
        out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      carry = all.slice(Math.floor(n * ratio));
      pending.push(out);
      pendingLen += n;
      if (pendingLen >= 1600 && ws.readyState === WebSocket.OPEN) {
        const buf = new Int16Array(pendingLen);
        let o = 0;
        for (const p of pending) {
          buf.set(p, o);
          o += p.length;
        }
        ws.send(buf.buffer);
        pending = [];
        pendingLen = 0;
      }
    };

    const release = async (): Promise<string> => {
      releasedAt = performance.now();
      const close = () =>
        setTimeout(() => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify({ type: "close" })), 1200);
      if (ws.readyState === WebSocket.CONNECTING) ws.addEventListener("open", close, { once: true });
      else close();
      const guard = new Promise<string>((res) => setTimeout(() => res([...turns, partial].join(" ").trim()), 6000));
      const text = await Promise.race([done, guard]);
      node.disconnect();
      src.disconnect();
      if (ws.readyState <= WebSocket.OPEN) ws.close();
      return text;
    };
    return { release };
  }
}
