"""Native PyTorch adapter for E2E-Spot's RegNet-Y 200MF + GSM + GRU.

Architecture adapted from jhong93/spot (BSD-3-Clause); see vendor/e2e_spot/LICENSE.
The unmodified vendored GSM retains its BSD-2-Clause notice. Its CUDA-only
allocation helpers are overridden below to allocate on the actual input device.
"""
from pathlib import Path
import importlib.util
import math

import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[2]
CLASSES = ['background', 'serve_left', 'serve_right', 'stroke_left', 'stroke_right']


def select_device(requested='auto'):
    if requested not in ('auto', 'cpu', 'mps', 'cuda'):
        raise ValueError('Unknown device')
    if requested == 'auto':
        return 'cuda' if torch.cuda.is_available() else ('mps' if torch.backends.mps.is_available() else 'cpu')
    if requested == 'mps' and not torch.backends.mps.is_available():
        raise RuntimeError('MPS unavailable; choose cpu explicitly or run with native GPU access')
    if requested == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable')
    return requested


spec = importlib.util.spec_from_file_location('trophy_original_gsm', ROOT / 'vendor/e2e_spot/gsm.py')
gsm_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gsm_module)


class NativeGSM(gsm_module._GSM):
    def lshift_zeroPad(self, x):
        return torch.cat((x[:, :, 1:], torch.zeros_like(x[:, :, :1])), dim=2)

    def rshift_zeroPad(self, x):
        return torch.cat((torch.zeros_like(x[:, :, :1]), x[:, :, :-1]), dim=2)


class GatedShift(nn.Module):
    def __init__(self, net):
        super().__init__()
        channels = net.in_channels if isinstance(net, nn.Conv2d) else net.conv.in_channels
        self.fold_dim = math.ceil(channels // 4 / 4) * 4
        self.gsm = NativeGSM(self.fold_dim, 1)
        self.net = net

    def forward(self, x):
        return self.net(torch.cat((self.gsm(x[:, :self.fold_dim]), x[:, self.fold_dim:]), dim=1))


class FCPrediction(nn.Module):
    def __init__(self, features, classes):
        super().__init__()
        self._fc_out = nn.Linear(features, classes)

    def forward(self, x):
        return self._fc_out(x)


class GRUPrediction(nn.Module):
    def __init__(self, features, classes):
        super().__init__()
        self._gru = nn.GRU(features, features, batch_first=True, bidirectional=True)
        self._fc_out = FCPrediction(features * 2, classes)
        self._dropout = nn.Dropout(.5)

    def forward(self, x):
        y, _ = self._gru(x)
        return self._fc_out(self._dropout(y))


class ServeSpotter(nn.Module):
    def __init__(self, classes=len(CLASSES)):
        super().__init__()
        import timm
        self._features = timm.create_model('regnety_002', pretrained=False)
        dimension = self._features.head.fc.in_features
        self._features.head.fc = nn.Identity()
        for stage in [self._features.s1, self._features.s2, self._features.s3, self._features.s4]:
            for block in stage.children():
                block.conv1 = GatedShift(block.conv1)
        self._pred_fine = GRUPrediction(dimension, classes)

    def encode(self, x):
        b, t, c, h, w = x.shape
        for module in self.modules():
            if isinstance(module, NativeGSM):
                module.num_segments = t
        return self._features(x.reshape(b * t, c, h, w)).reshape(b, t, -1)

    def forward(self, x):
        return self._pred_fine(self.encode(x))

    def initialize(self, path):
        """Reuse published visual/temporal weights; replace only the sport label head."""
        state = torch.load(path, map_location='cpu', weights_only=True)
        head = '_pred_fine._fc_out._fc_out.'
        filtered = {k: v for k, v in state.items() if not k.startswith(head)}
        result = self.load_state_dict(filtered, strict=False)
        expected = {head + 'weight', head + 'bias'}
        if set(result.missing_keys) != expected or result.unexpected_keys:
            raise ValueError(f'Initialization architecture mismatch: {result}')
        return dict(loaded_tensors=len(filtered), replaced_keys=sorted(expected))


def load_checkpoint(path, device='auto'):
    selected = select_device(device)
    checkpoint = torch.load(Path(path), map_location='cpu', weights_only=True)
    if checkpoint.get('format') != 'trophy-serve-spotter-v1' or checkpoint.get('classes') != CLASSES:
        raise ValueError('Expected a trained Trophy serve checkpoint, not tennis initialization weights')
    model = ServeSpotter()
    model.load_state_dict(checkpoint['state_dict'], strict=True)
    model.eval().to(selected)
    return model, checkpoint, selected
