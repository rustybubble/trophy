# Handoff validation — October 24, 2026

Validated in a separate Trophy Git worktree on Apple Silicon macOS, using
Python 3.12 and MPS. This is a fresh local environment/asset restoration test;
execution on the receiving computer has not yet been measured.

- Installed all four environments from the committed locks, without the original
  environment's cross-checkout `.pth`. Also ran the default bootstrap that creates
  its own pinned installer.
- Doctor passed all runtime imports and the 33 required runtime/recording/sample
  asset checks.
- Imported the complete private tar, then separately verified all **1,602** asset
  checksums: no missing or mismatched files.
- **136 Python tests and 19 JavaScript tests passed.**
  The final entry point used Node 24.19.0 through `TROPHY_NODE`; this machine's
  unrelated Homebrew Node installation had a missing dynamic library. Doctor now
  checks Node explicitly, and the handoff supports an executable override.
- Fresh `public-smoke` inference, triangulation, synchronization, serve detection,
  HMR2 inference and body fitting passed integrity/reference checks: **59 body
  frames**, **20 valid ball frames**, **2.7684 px** median body reprojection error,
  original-camera offset **+0.007569543 s**.
- Fresh `room-demo-15s` reran both uploaded recordings through the full pipeline
  and passed all integrity/reference tolerances: **369 body frames**, **108 valid
  ball frames**, **8.3705 px** median body reprojection error and original-camera
  offset **−0.091983800 s**. Body playback spans **2.7–14.9667 s** of the 15-second
  analyzed prefix. The archived fit was 8.3625 px; this small numerical difference
  is why the reference checks use declared tolerances.
- Fresh `toss-original` decoded and tracked the restored original recordings and
  rendered a **600-frame / 20-second MP4**. Its estimates match the archived demo:
  **8.690385 cm** release-to-apex rise and **30.718582°** direction. These remain
  demonstration estimates with a manually reviewed release and approximate camera
  geometry; they are not validated officiating measurements.
- Fresh `serves-original` inference completed on both restored original recordings
  and produced **6 merged serve candidates**. Candidate count is not an accuracy
  measurement; the reviewed/automatic quality gates remain intact.
- Fresh `legacy-hmr2` neural inference, multiview fit and native MP4 rendering
  completed: **87 body frames**, **5.1550 px** median body reprojection error.
- Fresh `ball-only` refinement and completion reproduced **305 triangulated
  frames**, **57 estimated gap frames**, **88 unavailable frames**, and **362/450
  visible ball frames**. All three 1920×1080 / 30 fps MP4s verified as 450 frames.
  The 4.4–15.0 s editing excerpt also verified as **318 frames / 10.6 s**.
  Original triangulations remain separate from display estimates. This is a
  refinement/completion of cached detections, not new detector inference.

Fresh outputs were written under ignored `artifacts/reproductions/validation-*`;
the imported reference outputs were preserved. The private tar is the immutable
reference kit described in `../REPRODUCE.md`; new verification outputs are not
silently substituted into it.

The final 7,105,792,000-byte kit was imported once more into an empty temporary
directory and every restored file rehashed: **1,602 verified, zero missing, zero
mismatched**. Only the final archive/checksum pair is retained for transfer.
