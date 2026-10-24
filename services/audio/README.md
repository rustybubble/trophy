# Audio (owner B)

**Env:** py3.11 · librosa 0.11.0 · panns_inference

## Responsibilities
- Phones do onset detection in an AudioWorklet (10 kHz high-pass + 1 ms energy) and send `audio_onset` + a 150 ms PCM snippet.
- This service classifies snippets with PANNs CNN14 embeddings + logistic regression: table / racket / floor / net / **rim** / bag-on-board / bag-in-hole / chains. Collect about 50 snippets per class at the event.
- PANNs downloads its weights with `wget`, so pre-place the weight files. Emit to `ev:audio`.

## Done when
See the matching feature in `docs/plan/build-plan.md` ("Done when"). Record measured numbers in `docs/progress.md`.
