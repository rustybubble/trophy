# Prompt 1 — import two camera videos and synchronize them

Implement a usable two-camera recorded-game import flow in **`/Users/mudu/Developer/trophy`**. A user should select two recordings of the same rally, obtain a proposed shared timeline, inspect synchronized playback, correct the offset if necessary, and start offline reconstruction. Uploaded labels must not be required.

First read `AGENTS.md`, `CLAUDE.md`, current `packages/contracts/` schemas, `docs/plan/interfaces-v1.md`, and the current gateway, recorder, clip-player and Watch implementations. Inspect the receiving branch: some planning documents describe code that may live on another branch. Build on existing upload/jobs/recording facilities where available. Agent 1 owns shared contracts; preserve existing work and coordinate schema changes through the repo's process.

Reference implementation:

- `/Users/mudu/Developer/calhacks/scripts/probe_audio_sync.py`
- `/Users/mudu/Developer/calhacks/tests/test_audio_sync_probe.py`
- `/Users/mudu/Developer/calhacks/UNLABELED_MULTIVIEW.md`
- `/Users/mudu/Developer/calhacks/HMR2_REPLAY.md`

Requirements:

1. Import two videos into ignored local recording storage, with explicit camera identity, duration, display orientation, resolution, source timestamps and audio availability. Use presentation timestamps, including variable-frame-rate media; do not assume `frame_index / 60`. Keep originals intact. Preserve game/camera authentication and scoped artifact access.
2. Adapt the audio correlation probe for coarse alignment. Search the actual overlapping clip durations instead of a hardcoded ±250 ms. Reject weak, ambiguous, boundary-peaked or insufficient-overlap matches. Handle missing audio and unrelated recordings with an actionable state and manual alignment. Explain the offset sign with one documented equation. Audio alignment is a proposal for image alignment: A/V latency and acoustic travel can shift the visual optimum.
3. Show both source videos with a common playhead, seek controls and a manual offset adjustment. Save the accepted alignment, its method, evidence and source fingerprint. For longer clips, compare windowed offsets and report clock drift; apply a fitted drift only when adequately supported. Preserve room for the later visual refinement from ball reconstruction.
4. Define a versioned reconstruction manifest and job lifecycle using the existing gateway conventions: source references, media-time-to-`t_game_s` mappings, overlap, alignment status, calibration references, stage/progress/error, and artifact references. These are new contracts to implement, not existing API names. Include input/config/model versions so cached output is not reused for different inputs. Publish artifacts atomically; a partial job must not look complete.
5. Keep video/large artifacts in recorder storage, with metadata only in Spacetime. Imported-file alignment must not replace the live gateway's phone clock fit. Copy source-derived game times into downstream measurements.

Acceptance: demonstrate both supplied recordings over a selected overlapping interval; test offset sign, a known shift, unequal/VFR timestamps, ambiguous or unrelated audio, no audio, no overlap, and manual correction. Distinguish synthetic test signals from real-footage validation. UI must make alignment uncertainty visible without exposing internal implementation detail. Report the manifest contract and exact next-stage invocation; update relevant docs/status with measured results.

Local recordings for validation:

```text
/Users/mudu/Developer/trophy/data/ttClips/Adobe Express - IMG_4342.mp4
/Users/mudu/Developer/trophy/data/ttClips/IMG_2865 (1).mov
```
