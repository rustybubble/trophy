"""Clock-sign and rejection checks; synthetic signals are not tracking evidence."""
import numpy as np
import pytest

from scripts.probe_audio_sync import align_audio, audio_envelope, ENVELOPE_HZ


@pytest.mark.parametrize('delay', [-120, -7, 0, 7, 120])
def test_audio_lag_sign_and_recovery(delay):
    envelope = np.random.default_rng(42).normal(size=1000)
    a = np.pad(envelope, (max(0, -delay), 0))
    b = np.pad(envelope, (max(0, delay), 0))
    found, score = align_audio(a, b, max_lag_seconds=2)
    assert found == pytest.approx(delay / ENVELOPE_HZ)
    assert score > .99


def test_audio_correlation_rejects_silence():
    with pytest.raises(ValueError, match='Weak audio correlation'):
        align_audio(np.zeros(500), np.zeros(500))


def test_audio_correlation_rejects_boundary_optimum():
    envelope = np.random.default_rng(42).normal(size=1000)
    with pytest.raises(ValueError, match='search boundary'):
        align_audio(envelope, np.pad(envelope, (200, 0)), max_lag_seconds=1)


def test_missing_audio_is_explicit():
    # Existing inference previews intentionally omit audio.
    from pathlib import Path
    preview = Path('artifacts/unlabeled-investigation/blurball-smoke/annotated.mp4')
    if not preview.exists():
        pytest.skip('Run the inference smoke probe first')
    with pytest.raises(ValueError, match='No audio stream'):
        audio_envelope(preview)
