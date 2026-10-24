# Evals

Labelled calls power the sport wall's accuracy and, later, calibration of the AI-vote probabilities. **No accuracy number without a labelled set.**

- `evals/labels/<sport>/<clip_id>.jsonl`: one line per call: `{t_game_s, rule_id, truth_outcome, labeller, source}`. Sources: staged event clips, score overlays from the clip library, the Trophy Watch review queue.
- Metrics: per-call accuracy with Wilson 95% CI; a reliability diagram per Snap-judged rule type; event P/R (courtcam event-eval / MOT metrics).
- Synthetic fixtures (e.g. `courtcam synth`) live under `evals/synthetic/` and are **always labelled synthetic**.
