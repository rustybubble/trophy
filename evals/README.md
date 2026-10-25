# Evals

Labelled calls power the sport wall's accuracy and, later, calibration of the AI-vote probabilities. **No accuracy number without a labelled set.**

- `evals/labels/<sport>/<clip_id>.jsonl`: one line per call: `{t_game_s, rule_id, truth_outcome, labeller, source}`. Sources: staged event clips, score overlays from the clip library, the Trophy Watch review queue.
- Metrics: per-call accuracy with Wilson 95% CI; a reliability diagram per Snap-judged rule type; event P/R (courtcam event-eval / MOT metrics).
- Synthetic fixtures (e.g. `courtcam synth`) live under `evals/synthetic/` and are **always labelled synthetic**.

## Live-path evaluation and re-recording

`tools/eval_live.py` exports a frozen Spacetime/recorder snapshot, initializes empty labels, validates them,
and scores rally outcomes, edge/side, serve faults, wrong boundaries and no-ball false positives with Wilson
95% intervals. It does not run or change the tracker. Procedures, label formats, independent splits, source
hashes, legal-serve coverage and consent: [demo-setup.md](../docs/demo-setup.md).

Store real labels/predictions/reports in `data/local/evals/`. The small files under `evals/fixtures/synthetic/`
are explicitly synthetic evaluator examples, not game-accuracy results.
