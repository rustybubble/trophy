"""Local image corner selector returning coordinates in the original frame."""
import base64

import cv2
import numpy as np
import streamlit.components.v1 as components

from trophy.session import ROOT

_component = components.declare_component('table_corner_picker', path=str(ROOT / 'web/corner-picker'))


def selected_corners(value, width, height):
    """Validate the component boundary before passing points to calibration."""
    if value is None or isinstance(value, list) and not value:
        return [[None, None] for _ in range(4)]
    points = np.asarray(value, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) > 4:
        raise ValueError('Corner selection must contain up to four image points')
    if not np.isfinite(points).all() or np.any(points < 0) or np.any(points >= [width, height]):
        raise ValueError('Selected table corners must lie within the source image')
    return points.tolist() + [[None, None] for _ in range(4-len(points))]


def pick_corners(frame, key, initial_points=None):
    height, width = frame.shape[:2]
    # Keep the preview light; coordinates returned by the component are always
    # scaled to the full source resolution, even after responsive resizing.
    scale = min(1., 1200 / width)
    preview = cv2.resize(frame, (round(width*scale), round(height*scale))) if scale < 1 else frame
    ok, encoded = cv2.imencode('.jpg', preview, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise ValueError('Cannot prepare corner-selection preview')
    value = _component(image='data:image/jpeg;base64,' + base64.b64encode(encoded).decode('ascii'),
                       source_width=width, source_height=height, initial_points=initial_points,
                       key=key, default=initial_points)
    return selected_corners(value, width, height)
