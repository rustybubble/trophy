/** The runner's view of an agent: one prompt per turn, events as they happen. The Droid SDK implements it. */
import type { DroidRunStep } from "@trophy/contracts";

export type AgentEvent = Omit<DroidRunStep, "t_ms">;

export interface AgentTurnResult {
  success: boolean;
  text: string;
  error?: string;
  tokenUsage?: { input: number; output: number };
}

export interface Agent {
  turn(prompt: string, onEvent: (e: AgentEvent) => void, signal: AbortSignal): Promise<AgentTurnResult>;
  close(): Promise<void>;
}

export interface AgentContext {
  sandboxDir: string;
  allowlist: readonly string[];
  /** The job's gate script name (`replay_test` | `check_test`); the only command the handler lets through */
  gate?: string;
  model: string;
  reasoningEffort?: string;
}

export type AgentFactory = (ctx: AgentContext) => Promise<Agent>;
