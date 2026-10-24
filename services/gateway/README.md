# Gateway (owner A)

**Env:** py3.11 · FastAPI · port 8000

## Responsibilities
- WebRTC signaling (`POST /offer` → ingest), the NTP-style clock-sync WebSocket, and the QR-timecode calibration endpoint (build plan F2).
- Signed GCS upload URLs for rally chunks and full recordings (resumable).
- Short-lived tokens for phones (Cartesia `/access-token`, scoped share tokens).
- Serves nothing static; Caddy serves `apps/*/dist`.
- Game state does **not** live here. It lives in SpacetimeDB.

## Done when
See the matching feature in `docs/plan/build-plan.md` ("Done when"). Record measured numbers in `docs/progress.md`.
