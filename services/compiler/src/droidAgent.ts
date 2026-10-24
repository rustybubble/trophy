/**
 * The Factory Droid behind the runner's `Agent` interface (@factory/droid-sdk 0.10.0, Node entrypoint).
 *
 * Scoped access: the session runs with autonomy OFF, so every edit, create and shell command comes back to our
 * permission handler. It proceeds only for edits inside the job's allowlist and for `./replay_test`; everything else
 * is cancelled and recorded as a `blocked` step. Web, task, skill and automation tools are disabled outright.
 */
import {
  AutonomyLevel,
  DroidMessageType,
  ToolConfirmationOutcome,
  ToolConfirmationType,
  createSession,
  type CreateSessionOptions,
} from "@factory/droid-sdk/node";

import type { Agent, AgentContext, AgentEvent, AgentFactory, AgentTurnResult } from "./agent.ts";
import { isAllowedCommand, isAllowedEdit } from "./allowlist.ts";

export const DISABLED_TOOLS = [
  "FetchUrl",
  "WebSearch",
  "Task",
  "Skill",
  "GenerateImage",
  "Loop",
  "StageSettingsChanges",
  "ListAutomations",
  "ListAutomationTemplates",
  "ReadAutomation",
  "CreateAutomation",
  "DeleteAutomation",
  "EditAutomation",
  "RunAutomation",
  "GenerateDroid",
  "ProposeMission",
  "StartMissionRun",
];

export const SYSTEM_APPEND = [
  "You are Trophy's sport-module compiler running inside a throwaway sandbox.",
  "You may only edit the files listed under 'Allowlist' in TASK.md and may only run `./replay_test`.",
  "Any other edit or command is refused by the runner; do not retry it, work within the allowlist.",
  "Begin your first reply with a '## Plan' section (3-6 numbered steps), then do the work, then end with '## Result'.",
].join(" ");

interface Opts {
  apiKey: string;
  execPath: string | undefined;
}

type Details = { type: string; filePath?: string; fullCommand?: string; command?: string; calls?: ScriptCall[] };
type ScriptCall = { toolName?: string; confirmation?: Details };
type ToolUse = { details: Details };

export function decide(ctx: AgentContext, toolUses: ToolUse[], onBlocked: (what: string) => void): boolean {
  if (!toolUses.length) return false;
  for (const tu of toolUses) {
    const d = tu.details;
    switch (d.type) {
      case ToolConfirmationType.Script: {
        // Script mode (claude-opus-5-5, claude-fable-5.1, gpt-6-sol in SDK sessions, measured 2026-10-24) runs file
        // edits inside a script the handler can only partly inspect, so the compiler refuses it and uses a model that
        // runs in direct tool mode (claude-sonnet-5, claude-opus-4-8). DROID_MODEL picks it.
        onBlocked("script refused: script-mode tool execution is not supported; use a direct-tool model");
        return false;
      }
      case ToolConfirmationType.Edit:
      case ToolConfirmationType.Create:
      case ToolConfirmationType.ApplyPatch: {
        if (!d.filePath || !isAllowedEdit(ctx.sandboxDir, d.filePath, ctx.allowlist)) {
          onBlocked(`edit outside the allowlist: ${d.filePath ?? "?"}`);
          return false;
        }
        break;
      }
      case ToolConfirmationType.Execute: {
        const cmd = d.fullCommand ?? d.command ?? "";
        if (!isAllowedCommand(cmd, ctx.sandboxDir)) {
          onBlocked(`command refused: ${cmd.slice(0, 160)}`);
          return false;
        }
        break;
      }
      default:
        onBlocked(`tool refused: ${d.type}`);
        return false;
    }
  }
  return true;
}

function pathOf(input: unknown): string | undefined {
  if (!input || typeof input !== "object") return undefined;
  const o = input as Record<string, unknown>;
  for (const k of ["file_path", "filePath", "path", "target_file"]) {
    if (typeof o[k] === "string") return o[k] as string;
  }
  return undefined;
}

function commandOf(input: unknown): string | undefined {
  if (!input || typeof input !== "object") return undefined;
  const o = input as Record<string, unknown>;
  return typeof o.command === "string" ? o.command : undefined;
}

export function droidAgentFactory(opts: Opts): AgentFactory {
  return async (ctx) => {
    let blockedSink: (what: string) => void = () => {};
    const options: CreateSessionOptions = {
      cwd: ctx.sandboxDir,
      apiKey: opts.apiKey,
      execPath: opts.execPath,
      modelId: ctx.model,
      reasoningEffort: ctx.reasoningEffort as CreateSessionOptions["reasoningEffort"],
      // "low" is the lowest level that offers the Edit/Create tools; it auto-approves edits, so the sandbox's
      // PreToolUse hook (hooks/guard.py) is the enforcement point and this handler is the second line.
      autonomyLevel: AutonomyLevel.Low,
      disableBuiltinSkills: true,
      disabledToolIds: DISABLED_TOOLS,
      systemPrompt: { type: "preset", preset: "droid", append: SYSTEM_APPEND },
      env: { PATH: process.env.PATH ?? "", HOME: process.env.HOME ?? "", FACTORY_API_KEY: opts.apiKey },
      permissionHandler({ toolUses, options: offered }) {
        const ok = decide(ctx, toolUses as unknown as ToolUse[], (w) => blockedSink(w));
        const want = ok ? ToolConfirmationOutcome.ProceedOnce : ToolConfirmationOutcome.Cancel;
        if (offered.some((o) => o.value === want)) return want;
        return ToolConfirmationOutcome.Cancel;
      },
    };
    const session = await createSession(options);
    const agent: Agent = {
      async turn(prompt, onEvent, signal) {
        blockedSink = (what) => onEvent({ kind: "blocked", text: what });
        let text = "";
        let result: AgentTurnResult = { success: false, text: "", error: "no result message" };
        for await (const msg of session.stream(prompt, { abortSignal: signal })) {
          switch (msg.type) {
            case DroidMessageType.Assistant:
              text += msg.text;
              if (msg.text.trim()) onEvent({ kind: "message", text: msg.text.trim().slice(0, 2000) });
              break;
            case DroidMessageType.ToolCall: {
              const name = msg.name;
              const p = pathOf(msg.input);
              const cmd = commandOf(msg.input);
              let kind: AgentEvent["kind"] = "tool";
              if (["Edit", "Create", "ApplyPatch", "Write", "MultiEdit"].includes(name)) kind = "edit";
              if (name === "Execute" && cmd && /replay_test/.test(cmd)) kind = "test";
              onEvent({
                kind,
                tool: name,
                path: p,
                text: cmd ? `${name}: ${cmd.slice(0, 200)}` : p ? `${name}: ${p}` : name,
              });
              break;
            }
            case DroidMessageType.ToolResult:
              if (msg.isError) {
                const c = typeof msg.content === "string" ? msg.content : JSON.stringify(msg.content);
                onEvent({ kind: "error", tool: msg.toolName, text: `${msg.toolName} failed: ${c.slice(0, 400)}` });
              }
              break;
            case DroidMessageType.Hook: {
              // The sandbox's PreToolUse guard: exit 2 blocked the call, with the reason on stderr.
              const h = msg as { status?: string; exitCode?: number | null; stderr?: string; eventName?: string };
              if (h.status !== "started" && h.exitCode === 2) {
                onEvent({ kind: "blocked", text: `guard: ${(h.stderr ?? "").trim().slice(0, 200)}` });
              }
              break;
            }
            case DroidMessageType.Error:
              onEvent({ kind: "error", text: msg.message });
              break;
            case DroidMessageType.Result:
              result = {
                success: msg.success,
                text,
                error: msg.success ? undefined : (msg.error?.message ?? `turn ended: ${msg.subtype}`),
                tokenUsage: msg.tokenUsage
                  ? { input: msg.tokenUsage.inputTokens, output: msg.tokenUsage.outputTokens }
                  : undefined,
              };
              break;
          }
        }
        return result;
      },
      async close() {
        await session.close();
      },
    };
    return agent;
  };
}
