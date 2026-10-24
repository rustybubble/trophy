# Post-game GPU jobs (owner A/B), on Vultr

**Env:** Vultr L40S · py3.10/3.11 containers

## Responsibilities
- Practical-RIFE v4.25 (4× slow-mo; Python ≤ 3.11; weights on Google Drive), SAM 2.1 cutouts for 2.5D replay angles (Player's view, Orbit, Broadcast high), optional GVHMR (needs SMPL registration) and ReCamMaster (`KlingTeam/ReCamMaster-Wan2.1`, stretch).
- A job queue pulled from GCS / gateway. It also earns MLH Best Use of Vultr.

## Done when
See the matching feature in `docs/plan/build-plan.md` ("Done when"). Record measured numbers in `docs/progress.md`.
