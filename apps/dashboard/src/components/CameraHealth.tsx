import type { Camera } from "@trophy/state-client";

export function CameraHealth({ cameras }: { cameras: Camera[] }) {
  const cams = cameras.filter((c) => c.role.split(",").includes("cam"));
  return (
    <div className="panel">
      <h2>Cameras</h2>
      {!cams.length && <p className="muted">No camera phones yet. Scan the code to add one.</p>}
      <table className="small">
        <tbody>
          {cams.map((c) => (
            <tr key={c.cam_id}>
              <td className={c.connected ? "ok" : "bad"}>{c.connected ? "●" : "○"}</td>
              <td>{c.label || c.cam_id}</td>
              <td className="num">{c.fps_in.toFixed(1)} fps</td>
              <td className="num">±{c.sync_err_ms.toFixed(1)} ms</td>
              <td className={!c.calibration ? "muted" : c.calib_trusted ? "ok" : "warn"}>
                {c.calibration ? (c.calib_trusted ? "calibrated" : "calibration untrusted") : "not calibrated"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
