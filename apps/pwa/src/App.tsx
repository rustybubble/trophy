import { lazy, Suspense } from "react";

// The judging demo (D-42: phones show replayed angles) is the default. The original live-camera capture app stays
// reachable with ?mode=camera; each loads its own stylesheet, so they never share CSS.
const JudgeApp = lazy(() => import("./ui/JudgeApp.tsx"));
const LegacyApp = lazy(() => import("./legacy/LegacyApp.tsx"));

export function App() {
  const camera = new URLSearchParams(location.search).get("mode") === "camera";
  return <Suspense fallback={null}>{camera ? <LegacyApp /> : <JudgeApp />}</Suspense>;
}
