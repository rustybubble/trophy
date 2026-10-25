"""Inference adapter for the official 4D Humans HMR 2.0 checkpoint.

The released checkpoint contains the SMPL inference buffers. Use those exact
buffers with smplx.lbs rather than requiring a separate copy of the same model.
No learned weights, body templates or shape bases are synthesized here.
Upstream network implementations and source notices remain in vendor/4D-Humans.
"""
import hashlib
import os
from pathlib import Path
import sys

import cv2
import numpy as np
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT_SHA256 = 'c9ea09c834161468638c9de7a782c614e300c622709bf52967274c543ec72fcf'


def official_imports():
    os.environ.setdefault('PYOPENGL_PLATFORM', 'darwin' if sys.platform == 'darwin' else 'egl')
    os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'artifacts/hmr2-matplotlib'))
    sys.path.insert(0, str(ROOT / 'vendor/4D-Humans'))
    from hmr2.configs import get_config
    from hmr2.models.backbones import create_backbone
    from hmr2.models.heads import build_smpl_head
    return get_config, create_backbone, build_smpl_head


class CheckpointBody(nn.Module):
    """The original checkpoint's SMPL body, evaluated with official SMPL-X LBS."""
    REQUIRED = ['v_template', 'shapedirs', 'posedirs', 'J_regressor', 'parents',
                'lbs_weights', 'faces_tensor']

    def __init__(self, state):
        super().__init__()
        for name in self.REQUIRED:
            value = state.get('smpl.' + name)
            if value is None:
                raise ValueError(f'Official checkpoint is missing SMPL buffer {name}')
            self.register_buffer(name, value.detach().clone())
        if self.v_template.shape != (6890, 3) or self.parents.shape != (24,):
            raise ValueError('Unexpected body model dimensions')

    def forward(self, betas, rotations):
        from smplx.lbs import lbs
        return lbs(betas, rotations, self.v_template, self.shapedirs,
                   self.posedirs, self.J_regressor, self.parents,
                   self.lbs_weights, pose2rot=False)


class HMR2Inference(nn.Module):
    def __init__(self, checkpoint, config, device='cpu'):
        super().__init__()
        checkpoint = Path(checkpoint)
        if os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK') == '1':
            raise ValueError('Disable implicit MPS CPU fallback for verified inference')
        with checkpoint.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != CHECKPOINT_SHA256:
            raise ValueError(f'Checkpoint checksum mismatch: {digest}')
        get_config, create_backbone, build_smpl_head = official_imports()
        cfg = get_config(str(config))
        cfg.defrost()
        cfg.SMPL.MEAN_PARAMS = str(ROOT / 'weights/hmr2-assets/data/smpl_mean_params.npz')
        cfg.MODEL.BBOX_SHAPE = [192, 256]
        cfg.freeze()
        self.cfg = cfg
        # This is the official upstream inference network, with strict matching
        # of every backbone/head parameter against the published checkpoint.
        self.backbone = create_backbone(cfg)
        self.smpl_head = build_smpl_head(cfg)
        data = torch.load(checkpoint, map_location='cpu', weights_only=False)
        state = data['state_dict']
        network = {k: v for k, v in state.items()
                   if k.startswith(('backbone.', 'smpl_head.'))}
        self.load_state_dict(network, strict=True)
        self.body = CheckpointBody(state)
        self.checkpoint_sha256 = digest
        self.device_name = device
        self.to(device).eval()

    def forward(self, image):
        features = self.backbone(image[:, :, :, 32:-32])
        params, camera, _ = self.smpl_head(features)
        rotations = torch.cat([params['global_orient'], params['body_pose']], dim=1)
        vertices, joints = self.body(params['betas'].float(), rotations.float())
        return dict(rotations=rotations, betas=params['betas'], camera=camera,
                    vertices=vertices, joints=joints)


def person_box(landmarks, width, height):
    lm = np.asarray(landmarks)
    keep = np.isfinite(lm).all(axis=1) & (lm[:, 2] > .35)
    points = lm[keep, :2]
    if len(points) < 8:
        raise ValueError('Insufficient pose landmarks for a person crop')
    low, high = points.min(axis=0), points.max(axis=0)
    # HMR2 receives an image crop, not MediaPipe's 3D pose. These image-derived
    # boxes identify players in this controlled experiment, replacing ViTDet.
    pad = (high - low) * .12
    return np.r_[np.maximum(low - pad, [0, 0]),
                 np.minimum(high + pad, [width, height])].astype(np.float32)


def preprocess_person(bgr, box):
    """Match upstream's RGB, antialias, square crop and 192x256 inner window."""
    from skimage.filters import gaussian
    low, high = box[:2], box[2:]
    center = (low + high) / 2
    width, height = high - low
    size = max(height, width * 256 / 192)
    factor = size / 256 / 2
    image = (gaussian(bgr, sigma=(factor - 1) / 2, channel_axis=2,
                      preserve_range=True) if factor > 1.1 else bgr)
    cx, cy = center
    source = np.array([[cx, cy], [cx, cy + size / 2],
                       [cx + size / 2, cy]], np.float32)
    target = np.array([[128, 128], [128, 256], [256, 128]], np.float32)
    affine = cv2.getAffineTransform(source, target)
    crop = cv2.warpAffine(image, affine, (256, 256), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT)
    rgb = np.ascontiguousarray(crop[:, :, ::-1]).astype(np.float32)
    rgb = (rgb / 255 - np.array([.485, .456, .406], np.float32)) / np.array(
        [.229, .224, .225], np.float32)
    return torch.from_numpy(rgb.transpose(2, 0, 1).copy()), center, float(size)
