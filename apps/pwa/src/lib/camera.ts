// Rear camera, pinned by deviceId (research: pwa-capture §1.2, build card 2A). On iOS the virtual
// "Back Dual/Triple Camera" auto-switches lenses, so we pick a physical lens by label (wide first).
export interface CameraInfo {
  stream: MediaStream;
  label: string;
  settings: MediaTrackSettings;
  fake: boolean;
}

const WIDE = [/^back camera$/i, /rückkamera|caméra arrière|cámara trasera/i];
const ULTRA = [/back ultra wide/i];
const AVOID = /dual|triple|front|telephoto/i;

function pick(devices: MediaDeviceInfo[]): MediaDeviceInfo | undefined {
  const cams = devices.filter((d) => d.kind === "videoinput");
  for (const re of [...WIDE, ...ULTRA]) {
    const d = cams.find((c) => re.test(c.label));
    if (d) return d;
  }
  return cams.find((c) => /back|rear|environment/i.test(c.label) && !AVOID.test(c.label));
}

export async function openRearCamera(w = 1280, h = 720, fps = 30): Promise<CameraInfo> {
  // 1) permission (labels are empty before it), 2) pick a physical lens, 3) stop and reacquire once
  const first = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: { ideal: "environment" } },
    audio: false,
  });
  const devices = await navigator.mediaDevices.enumerateDevices();
  const chosen = pick(devices);
  let stream = first;
  if (chosen) {
    first.getTracks().forEach((t) => t.stop());
    stream = await navigator.mediaDevices.getUserMedia({
      video: {
        deviceId: { exact: chosen.deviceId },
        width: { ideal: w },
        height: { ideal: h },
        frameRate: { ideal: fps },
      },
      audio: false,
    });
  } else {
    await first
      .getVideoTracks()[0]
      ?.applyConstraints({ width: { ideal: w }, height: { ideal: h }, frameRate: { ideal: fps } });
  }
  const track = stream.getVideoTracks()[0]!;
  return { stream, label: track.label, settings: track.getSettings(), fake: false };
}

/** A synthetic moving test pattern (?fake=1): lets the streaming path be tested without a camera. */
export function fakeCamera(w = 1280, h = 720, fps = 30): CameraInfo {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  const g = c.getContext("2d")!;
  let n = 0;
  const draw = () => {
    n++;
    g.fillStyle = "#14532d";
    g.fillRect(0, 0, w, h);
    g.fillStyle = "#1e3a8a";
    g.fillRect(w * 0.15, h * 0.45, w * 0.7, h * 0.3); // a "table"
    const x = w * (0.2 + 0.6 * ((Math.sin(n / 20) + 1) / 2));
    const y = h * 0.35 - Math.abs(Math.sin(n / 7)) * h * 0.25;
    g.fillStyle = "#fff";
    g.beginPath();
    g.arc(x, y, 9, 0, Math.PI * 2);
    g.fill();
    g.font = "28px system-ui";
    g.fillText(`SYNTHETIC TEST PATTERN  #${n}`, 24, 44);
  };
  draw();
  setInterval(draw, 1000 / fps);
  const stream = c.captureStream(fps);
  return { stream, label: "synthetic test pattern", settings: { width: w, height: h, frameRate: fps }, fake: true };
}
