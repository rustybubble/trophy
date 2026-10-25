# Recorded analysis: branch audit and reproducible handoff

The current remote Codex branch on October 24, 2026 is
`codex/serve-legality-demo` (starting at `ec98dd2`). The older
`codex/tt-demo-failure-status` remote was removed and retained as the archive tag
`archive/tt-demo-failure-status`; it is not the current working branch.

## Audit against the demonstrated working directory

The branch already included the latest standalone source in
`spikes/serve-analysis`: **132 matching source/config/test/web files**, with no
missing files in those compared directories. The three differences were intentional
portability improvements in the branch: command-line inputs for the actual toss
renderer and repository-relative original-recording paths in two configurations.
Those changes are retained. Third-party source-only snapshots and notices are also
retained; example photos/recordings omitted from those snapshots stay omitted.

A second comparison caught four ball-only experiment files added to the working
directory during the audit: `ball_completion.py`, its test, and the builder and
renderer scripts. They are included with a portable inspected-corner profile and
a `ball-only` reproduction target. This experiment preserves raw triangulations
separately from smoothed/interpolated/extrapolated display positions.

Already present: two-angle upload, automatic gray/blue table outlining with
click/drag correction, audio and visual synchronization, BlurBall inference and
triangulation, official HMR2 initialization and two-view SMPL fit, the missing-first-
root fix, static-video range serving, serve/toss source review, and placements.
This is the experimental recorded-analysis app, not a new integration into the
live Flight/Spacetime/engine contracts.

## Gaps closed by this handoff

- A complete, standalone HMR2 dependency lock, replacing reliance on a hidden
  `.pth` into another checkout's base environment.
- One bootstrap for four independently installed Python 3.12 environments.
- Exact, portable profiles for the two latest videos, public smoke sample,
  original serve recordings, toss demonstration and legacy HMR2 replay.
- A private kit and a committed manifest of 1,602 size/checksum-pinned assets:
  originals, exact models, samples, reference outputs and evaluation assets.
- Safe import/verification, a doctor command, result integrity/tolerance checks,
  new output directories, complete source/JavaScript test entry point and portable
  serving commands.
- Font fallback for the historical actual-footage MP4 renderer.
- A receiving-agent prompt and explicit limits on exact artifact restoration,
  cross-device numerical reproducibility, full-recording coverage and privacy.

The receiving agent must start at
[REPRODUCE.md](../spikes/serve-analysis/REPRODUCE.md), not assume a clone includes
the models or private recordings. The private 7.1 GB tar is transferred separately
by the owner; it is deliberately absent from Git under `CLAUDE.md` safeguards 3–4.
No new cloud resource, public media upload or shared schema change is required.
