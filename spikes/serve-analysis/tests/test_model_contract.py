from pathlib import Path
import os
import pytest

from trophy.model import Predictor


def test_unavailable_weights(tmp_path):
    with pytest.raises(FileNotFoundError, match='Weights unavailable'):
        Predictor(tmp_path / 'missing', device='cpu')


def test_untrusted_checkpoint_rejected_before_loading(tmp_path):
    path = tmp_path / 'fake-checkpoint'
    path.write_bytes(b'not the official checkpoint')
    with pytest.raises(ValueError, match='checksum'):
        Predictor(path, device='cpu')


def test_mps_fallback_is_explicitly_prohibited(monkeypatch):
    monkeypatch.setenv('PYTORCH_ENABLE_MPS_FALLBACK', '1')
    with pytest.raises(RuntimeError, match='silent model CPU fallback'):
        Predictor(device='cpu')
