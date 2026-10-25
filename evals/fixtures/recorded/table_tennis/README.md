# Recorded fixtures (real play, no media)

`g_6ghx0t5z_rally1.l1.jsonl`: BlurBall pixel samples from two iPhone clips of the team's own play on 2026-10-24,
streamed through the gateway as phones, plus the tapped-corner calibrations (`calib_untrusted`). 2,475 samples, 44 s.
`g_6ghx0t5z_rally1_live.l2.jsonl`: the 60 layer-2 events `trophy-live` produced from them, exactly as the engine saw
them. Both are labelled by the people who played: ONE rally (70.7-102.0 s), won by B. The hand-written pack called
five points on it (`called` in the labels); the gate's `calls:winner` row fails until a pack scores it as one point
to B. Nothing here identifies anyone: pixel coordinates, confidences and events only. The footage stays in
`data/local/` (gitignored). Bounce positions are not labelled (`bounces: []`, tolerances off); the outcome is.

`g_mhwxxzpb_label01`, `g_mnygz0qm_label01`, `g_tcfktwyn_label01` (added 2026-10-25): the same two clips re-streamed live
on the evidence branch, each labelled by the judge on the dashboard ("that was one rally, won by B") and exported by the
engine's `label_rally` (layer-2 events plus per-call evidence digests). `g_tcfktwyn` ran on the Droid-written pack: BlurBall
returned the false side-line bounce at conf 0.81 that time (0.68 in the first recording), so the pack called a double
bounce; the Droid's correction run (01M5RYXPPF6WP7WXAQDKSJN0ZD) fixed it and is the shipped pack.
