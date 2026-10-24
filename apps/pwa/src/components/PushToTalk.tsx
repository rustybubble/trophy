import { useRef, useState } from "react";
import type { Voice } from "../lib/voice.ts";

/**
 * Hold to talk -> Cartesia Ink-2. A release during the first-use mic permission prompt is remembered (the
 * spike's bug), so the turn always closes.
 */
export function PushToTalk(props: { voice?: Voice; onTranscript: (t: string) => void; onError: (m: string) => void }) {
  const [state, setState] = useState<"idle" | "listening" | "thinking">("idle");
  const [partial, setPartial] = useState("");
  const holding = useRef(false);
  const pending = useRef<Promise<{ release: () => Promise<string> }> | undefined>(undefined);

  const down = (e: React.PointerEvent) => {
    e.preventDefault();
    if (!props.voice || pending.current) return;
    holding.current = true;
    setPartial("");
    setState("listening");
    pending.current = props.voice.listen(setPartial);
    pending.current.catch((err: unknown) => {
      props.onError(`Mic: ${err instanceof Error ? err.message : String(err)}`);
      pending.current = undefined;
      setState("idle");
    });
  };

  const up = async () => {
    if (!holding.current) return;
    holding.current = false;
    const p = pending.current;
    if (!p) return;
    setState("thinking");
    try {
      const text = await (await p).release();
      setPartial(text);
      if (text) props.onTranscript(text);
    } catch {
      /* reported on press */
    } finally {
      pending.current = undefined;
      setState("idle");
    }
  };

  return (
    <div className="ptt">
      <button
        className={`talk ${state}`}
        disabled={!props.voice}
        onPointerDown={down}
        onPointerUp={() => void up()}
        onPointerCancel={() => void up()}
        onPointerLeave={() => void up()}
        onContextMenu={(e) => e.preventDefault()}
      >
        {state === "listening" ? "Listening…" : state === "thinking" ? "…" : "Hold to talk"}
      </button>
      {partial && <span className="partial">“{partial}”</span>}
    </div>
  );
}
