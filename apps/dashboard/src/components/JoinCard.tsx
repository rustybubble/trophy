import { useEffect, useState } from "react";
import QRCode from "qrcode";
import type { Session } from "../lib/api.ts";

export function JoinCard({ session }: { session: Session }) {
  const [svg, setSvg] = useState<string>();
  useEffect(() => {
    void QRCode.toString(session.joinUrl, {
      type: "svg",
      margin: 1,
      color: { dark: "#0f1115", light: "#ffffff" },
    }).then(setSvg);
  }, [session.joinUrl]);
  return (
    <div className="panel join">
      <h2>Join with a phone</h2>
      {svg && <div className="qr" dangerouslySetInnerHTML={{ __html: svg }} />}
      <p className="small">
        <a href={session.joinUrl}>{session.joinUrl.replace(/^https?:\/\//, "")}</a>
      </p>
      <p className="muted small">
        Game {session.gameId}. Put the camera side-on at the net line, landscape, on a fixed mount.
      </p>
    </div>
  );
}
