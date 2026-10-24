import { useState } from "react";

const ROLES = [
  { id: "cam", title: "Camera", hint: "Film the table from the side, at the net line." },
  { id: "cam,judge", title: "Camera + judge", hint: "One phone does it all (the weekend demo)." },
  { id: "display", title: "Scoreboard", hint: "Shows and speaks the score and calls." },
  { id: "display,judge", title: "Judge", hint: "Scoreboard plus uphold / overturn, undo and house rules." },
];

export function JoinView(props: {
  gameId: string;
  hasKey: boolean;
  busy: boolean;
  error?: string;
  onJoin: (label: string, role: string) => void;
}) {
  const [role, setRole] = useState("cam,judge");
  const [label, setLabel] = useState("");
  return (
    <main className="join">
      <h1>Join game</h1>
      <p className="muted mono">{props.gameId}</p>
      {!props.hasKey && <p className="error">This link has no join key. Scan the QR code again.</p>}
      <div className="roles" role="radiogroup" aria-label="What is this phone for?">
        {ROLES.map((r) => (
          <button
            key={r.id}
            role="radio"
            aria-checked={role === r.id}
            className={role === r.id ? "role on" : "role"}
            onClick={() => setRole(r.id)}
          >
            <strong>{r.title}</strong>
            <span>{r.hint}</span>
          </button>
        ))}
      </div>
      <label className="field">
        Name this phone (optional)
        <input value={label} maxLength={40} placeholder="e.g. Net cam" onChange={(e) => setLabel(e.target.value)} />
      </label>
      <button className="primary big" disabled={props.busy || !props.hasKey} onClick={() => props.onJoin(label, role)}>
        {props.busy ? "Joining…" : "Join"}
      </button>
      {props.error && <p className="error">{props.error}</p>}
      <p className="muted small">
        Cameras film the game for automatic calls. Everyone filmed should agree to it. Video stays on the referee laptop.
      </p>
    </main>
  );
}
