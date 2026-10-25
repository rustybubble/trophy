// What the judging UI writes and fetches. Clients write only through the gateway (POST /api/ctl); Spacetime is
// read-only for them. The mock backend (src/mock) implements the same surface with labelled-synthetic rows.
import type { Feed } from "@trophy/state-client";
import type { Api, AskAnswer, LiveScenario, Scenario } from "./api.ts";

export interface Backend {
  readonly mock: boolean;
  ctl(cmd: string, args?: Record<string, unknown>): Promise<unknown>;
  ask(question: string, context: object): Promise<AskAnswer>;
  scenarios(): Promise<Scenario[]>;
  goLive(scenarioId: string): Promise<LiveScenario>;
  stop(): Promise<unknown>;
  /** The phone-playable file of a feed (gateway path + token). */
  feedSrc(feed: Feed): string;
  /** The recorder clip for an angle and a game-time window, or undefined when there is no recorder (mock). */
  clipSrc(camId: string, t0S: number, t1S: number): string | undefined;
}

export class GatewayBackend implements Backend {
  readonly mock = false;
  constructor(readonly api: Api) {}
  ctl(cmd: string, args: Record<string, unknown> = {}) {
    return this.api.ctl(cmd, args);
  }
  ask(question: string, context: object) {
    return this.api.ask(question, context);
  }
  scenarios() {
    return this.api.scenarios();
  }
  goLive(scenarioId: string) {
    return this.api.goLive(scenarioId);
  }
  stop() {
    return this.api.stopScenario();
  }
  feedSrc(feed: Feed) {
    return this.api.mediaUrl(feed.video_url);
  }
  clipSrc(camId: string, t0S: number, t1S: number) {
    return this.api.replayClipUrl(camId, t0S, t1S);
  }
}
