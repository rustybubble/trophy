# Trophy implementation handoff

These are copy-and-paste task prompts for the agent working in **`/Users/mudu/Developer/trophy`**. The working research implementation is in **`/Users/mudu/Developer/calhacks`**. This pack does not change Trophy or assign work to another chat.

## Start here for the current request

[Full-clip reconstruction and demo-video exports](FULL-CLIP-DEMO.md) is the consolidated implementation prompt. It supersedes the short-interval acceptance scope below: process the complete synchronized overlap of both supplied recordings, integrate the reconstruction into Trophy, and actually export/inspect full-length videos plus useful editing excerpts. The separate prompts remain background references.

## Recommended order

1. [Two-video import and synchronization](01-import-and-sync.md) — establish the shared timeline and reconstruction job/artifact contract. Primarily Agent 1; synchronization logic touches Agent 2.
2. [Unlabeled ball inference and calibrated 3D reconstruction](02-ball-reconstruction.md) — Agent 2. Produces a useful ball-only replay before human reconstruction exists.
3. [4D Humans offline reconstruction](03-hmr2-worker.md) — players/perception area, coordinated with Agent 3. Depends on camera geometry and alignment from 1–2.
4. [Integrated source-video and 3D replay](04-replay-ui.md) — Agent 1. Can start against a small, explicitly synthetic manifest fixture after 1, then connect real outputs from 2–3.
5. Optional: [Per-player placement heatmaps](05-placement-heatmaps.md) — Agent 3 analytics and Agent 1 UI. Needs ball trajectories; does not need 4D Humans.

For one receiving agent, paste these in order. For the fastest visible result, finish 1–2 and the ball-only portion of 4, then add 3. The repository owners are coordination hints; inspect the receiving branch's current implementation before choosing files.

## What the prototype actually establishes

- Pretrained BlurBall inference runs without uploaded labels. Labels are needed to measure accuracy, not to run inference.
- Official HMR2 inference and a two-view body fit ran on the user's recordings. The completed output covers **2.9 seconds**, not the full recordings, and uses inspected calibration points and controlled player identities.
- The replay contains real inferred SMPL surfaces and independently triangulated ball measurements. It is an estimated reconstruction, not a validated physics simulator.
- The user-footage export has accepted ball measurements in **60/87 frames**. Body fitting reaches **5.2 px median image residual against model-produced landmarks**; that is not independent 3D accuracy.
- Automatic synchronization and camera calibration still need production work. Do not ship the demo's crop boxes, calibration points, camera compensation, or timing offset as general solutions.

Read `/Users/mudu/Developer/calhacks/HMR2_REPLAY.md` for the measured execution and limitations. The downloaded checkpoint and working outputs already exist locally; do not repeat the earlier claim that a separate SMPL download is necessarily missing.

## Starter message

```text
Work in our actual Trophy repo at /Users/mudu/Developer/trophy. Use the tested research code in /Users/mudu/Developer/calhacks as a reference, preserving its provenance and adapting it to Trophy's current contracts and services. Start with /Users/mudu/Developer/calhacks/handoff-prompts/01-import-and-sync.md. Implement and verify that task, then report changed files, checks, limitations, and the contract the next prompt should consume. Preserve existing work and inspect your current branch before editing. Do not treat research metrics or hardcoded demo inputs as production guarantees.
```

The other prompt files are also self-contained task messages. New job/manifest APIs described there are proposals to implement using current repo conventions, not claims that those APIs already exist.
