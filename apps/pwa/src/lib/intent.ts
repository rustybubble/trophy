// Push-to-talk intent parse (interfaces-v1 §16): client-side rules first. Anything that isn't a command is
// treated as a rules question for "ask the ref".
export type Intent =
  | { kind: "challenge" }
  | { kind: "undo" }
  | { kind: "score" }
  | { kind: "house_rule"; text: string }
  | { kind: "ask"; question: string }
  | { kind: "none" };

const clean = (s: string) =>
  s
    .trim()
    .replace(/^(hey |ok |okay )?trophy[,.!]?\s*/i, "")
    .replace(/\s+/g, " ")
    .trim();

export function parseIntent(transcript: string): Intent {
  const t = clean(transcript);
  const lower = t.toLowerCase().replace(/[.!?]+$/, "");
  if (!lower) return { kind: "none" };
  if (/^(i )?(challenge|challenging)( (that|this|the call|it))?$/.test(lower) || /^challenge\b/.test(lower)) {
    return { kind: "challenge" };
  }
  if (/^(undo|take (that|it) back|cancel (that|the last) call)\b/.test(lower)) return { kind: "undo" };
  if (/^(what'?s the score|score|what is the score)\b/.test(lower)) return { kind: "score" };
  const hr = t.match(/^(?:add (?:a )?(?:house )?rule|new (?:house )?rule|house rule)[:,]?\s*(.+)$/i);
  if (hr?.[1]) return { kind: "house_rule", text: hr[1].trim() };
  return { kind: "ask", question: t };
}
