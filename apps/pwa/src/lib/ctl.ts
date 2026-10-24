// The control socket (/api/ws/ctl): NTP-style pings for the gateway's clock fit (a burst of 20 at 50 ms,
// then one every 2 s, each carrying the previous completed exchange), onsets, health and call acks.
import { phoneMs } from "./frame.ts";

export interface SyncState {
  connected: boolean;
  offsetMs: number | null;
  syncErrMs: number | null;
}

export class CtlSocket {
  private ws: WebSocket | undefined;
  private prev: { t0: number; t1: number; t2: number; t3: number } | undefined;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private pings = 0;
  private stopped = false;
  private retry = 500;
  state: SyncState = { connected: false, offsetMs: null, syncErrMs: null };

  constructor(
    private readonly url: string,
    private readonly onState: (s: SyncState) => void = () => {},
  ) {}

  start(): void {
    this.stopped = false;
    this.connect();
  }

  stop(): void {
    this.stopped = true;
    clearTimeout(this.timer);
    this.ws?.close();
  }

  send(msg: Record<string, unknown>): void {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg));
  }

  onset(tPhoneMs: number, peak: number, energy: number): void {
    this.send({ type: "onset", t_phone_ms: tPhoneMs, peak, energy });
  }

  callAck(callId: string): void {
    this.send({ type: "call_ack", call_id: callId, t_phone_ms: phoneMs() });
  }

  health(h: Record<string, number | string>): void {
    this.send({ type: "health", ...h });
  }

  private connect(): void {
    const ws = new WebSocket(this.url);
    ws.onopen = () => {
      this.retry = 500;
      this.pings = 0;
      this.prev = undefined; // a reconnect may follow a page-lifecycle pause; start a fresh burst
      this.state = { ...this.state, connected: true };
      this.onState(this.state);
      this.ping();
    };
    ws.onmessage = (e) => {
      const t3 = phoneMs();
      const m = JSON.parse(String(e.data)) as Record<string, number | string>;
      if (m.type === "pong" && typeof m.t0 === "number") {
        this.prev = { t0: m.t0, t1: m.t1 as number, t2: m.t2 as number, t3 };
      } else if (m.type === "sync") {
        this.state = { ...this.state, offsetMs: m.offset_ms as number, syncErrMs: m.sync_err_ms as number };
        this.onState(this.state);
      }
    };
    ws.onclose = () => {
      clearTimeout(this.timer);
      this.state = { ...this.state, connected: false };
      this.onState(this.state);
      if (!this.stopped) setTimeout(() => this.connect(), (this.retry = Math.min(this.retry * 2, 5000)));
    };
    this.ws = ws;
  }

  private ping(): void {
    this.send({ type: "ping", t0: phoneMs(), ...(this.prev ? { prev: this.prev } : {}) });
    this.pings++;
    this.timer = setTimeout(() => this.ping(), this.pings < 20 ? 50 : 2000);
  }
}
