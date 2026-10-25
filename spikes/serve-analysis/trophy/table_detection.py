"""Image-based tabletop segmentation for the fixed-camera room demo.

Score full quadrilaterals against visible edges and tabletop appearance. No
recording-specific pixel coordinates or reference ball positions are used.
"""
from itertools import combinations

import cv2
import numpy as np

from trophy.session import calibrate_camera


def tabletop_quad(image):
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    detected = cv2.createLineSegmentDetector().detect(gray)[0]
    if detected is None:
        return None
    lines = detected[:, 0]
    lengths = np.linalg.norm(lines[:, :2]-lines[:, 2:], axis=1)
    angles = np.arctan2(lines[:, 3]-lines[:, 1], lines[:, 2]-lines[:, 0])
    angles = (angles+np.pi/2) % np.pi-np.pi/2
    keep = ((lengths > w*.045) & (np.minimum(lines[:, 1], lines[:, 3]) > h*.35) &
            (np.maximum(lines[:, 1], lines[:, 3]) < h*.92) & (abs(angles) < np.radians(70)))
    lines, lengths, angles = lines[keep], lengths[keep], angles[keep]
    chosen = []
    for i in np.argsort(lengths)[::-1]:
        line = lines[i]
        equation = np.cross(np.r_[line[:2], 1], np.r_[line[2:], 1])
        equation /= np.linalg.norm(equation[:2])
        equation *= 1 if equation[1] > 0 else -1
        if any(np.linalg.norm(equation[:2]-e[:2]) < .035 and abs(equation[2]-e[2]) < 3 for e, _ in chosen):
            continue
        chosen.append((equation, angles[i]))
        if len(chosen) >= 45:
            break
    if len(chosen) < 4:
        return None
    equations = np.array([e for e, _ in chosen])
    angles = np.array([a for _, a in chosen])
    intersections = np.cross(equations[:, None], equations[None, :])
    intersections[:, :, -1] = np.where(abs(intersections[:, :, -1]) < 1e-7, np.nan, intersections[:, :, -1])
    xy = intersections[:, :, :2]/intersections[:, :, -1:]
    horizontal = np.where(abs(angles) < np.radians(18))[0]
    sides = np.where(abs(angles) > np.radians(4))[0]
    pairs = np.array(list(combinations(sides, 2)))
    if not len(pairs):
        return None
    candidates = []
    for a, b in combinations(horizontal, 2):
        available = pairs[(pairs != a).all(1) & (pairs != b).all(1)]
        if not len(available):
            continue
        c, d = available.T
        q = np.stack([xy[a, c], xy[a, d], xy[b, d], xy[b, c]], 1)
        good = (np.isfinite(q).all((1, 2)) & (q[:, :, 0] > 8).all(1) &
                (q[:, :, 0] < w-8).all(1) & (q[:, :, 1] > h*.35).all(1) & (q[:, :, 1] < h*.9).all(1))
        edges = np.roll(q, -1, axis=1)-q
        turns = np.cross(edges, np.roll(edges, -1, axis=1))
        good &= (turns > 0).all(1) | (turns < 0).all(1)
        area = abs(np.cross(q, np.roll(q, -1, axis=1)).sum(1))/2
        good &= ((area > w*h*.008) & (area < w*h*.25) &
                 (np.ptp(q[:, :, 0], axis=1) > w*.3) & (np.ptp(q[:, :, 1], axis=1) > h*.025))
        candidates.extend(q[good])
    if not candidates:
        return None
    q = np.array(candidates)
    area = abs(np.cross(q, np.roll(q, -1, axis=1)).sum(1))/2
    u = np.linspace(.1, .9, 20)[None, :, None]
    v = np.linspace(.15, .85, 8)[None, :, None, None]
    top = q[:, 0, None]*(1-u)+q[:, 1, None]*u
    bottom = q[:, 3, None]*(1-u)+q[:, 2, None]*u
    grid = np.rint(top[:, None]*(1-v)+bottom[:, None]*v).astype(int)
    xx, yy = grid[..., 0], grid[..., 1]
    surface_mask = ((hsv[:, :, 2] > 90) & (hsv[:, :, 2] < 225) &
                    (lab[:, :, 2] < 136) & (hsv[:, :, 1] < 110))
    surface = surface_mask[yy, xx].mean((1, 2))
    variation = gray[yy, xx].std((1, 2))
    distance = cv2.distanceTransform(255-cv2.Canny(gray, 40, 100), cv2.DIST_L2, 3)
    t = np.linspace(.03, .97, 40)[None, None, :, None]
    boundary = np.rint(q[:, :, None]*(1-t)+np.roll(q, -1, axis=1)[:, :, None]*t).astype(int)
    support = np.exp(-distance[boundary[..., 1], boundary[..., 0]]/2).mean(2)
    # A net can have stronger edges than the far table border. Look past each
    # edge: continuing tabletop appearance outside it suggests a partial table.
    edge_vectors = np.roll(q, -1, axis=1)-q
    normals = np.stack([-edge_vectors[..., 1], edge_vectors[..., 0]], axis=-1)
    normals /= np.maximum(1e-6, np.linalg.norm(normals, axis=-1, keepdims=True))
    midpoints = (q+np.roll(q, -1, axis=1))/2
    normals *= np.where((normals*(midpoints-q.mean(1)[:, None])).sum(-1) >= 0, 1, -1)[..., None]
    beyond = boundary+normals[:, :, None]*18
    bx = np.clip(np.rint(beyond[..., 0]).astype(int), 0, w-1)
    by = np.clip(np.rint(beyond[..., 1]).astype(int), 0, h-1)
    continuation = surface_mask[by, bx].mean((1, 2))
    # Reward the full table instead of treating the net as its far boundary.
    score = (area/(w*h))**1.5 * support.mean(1)**2 * np.sqrt(support.min(1)) * surface**3 * np.exp(-variation/90)
    score *= (1-.75*continuation)**4
    best = int(score.argmax())
    if surface[best] < .7 or support[best].min() < .45 or score[best] < .0002:
        return None
    return q[best], dict(edge_support=float(support[best].mean()), surface_fraction=float(surface[best]),
                         ranking_score=float(score[best]))


def detect_table(frame):
    """Return an editable full-resolution polygon plus approximate calibration."""
    h, w = frame.shape[:2]
    scale = min(1., 960/w)
    image = cv2.resize(frame, (round(w*scale), round(h*scale))) if scale < 1 else frame
    detected = tabletop_quad(image)
    if detected is None:
        return None
    quad, evidence = detected
    quad = quad / [image.shape[1]/w, image.shape[0]/h]
    rois = [[0, 0, w//2, h], [w//2, 0, w, h]]
    fits = []
    for direction in [1, -1]:
        for shift in range(4):
            points = np.roll(quad[::direction], shift, axis=0)
            for fraction in [.65, .9, 1.3, 1.8, 2.5]:
                view = dict(table_corners_px=points.tolist(), player_rois_px=rois,
                            focal_px=w*fraction, calibration_mode='automatic_demo')
                try:
                    _, report = calibrate_camera(view, dict(width=w, height=h))
                except ValueError:
                    continue
                # A moderate focal prior resolves near-side-on aspect ambiguity.
                objective = report['table_corner_rmse_px']/w + .002*abs(np.log(fraction/.9))
                fits.append((objective, points, w*fraction, report))
    if not fits:
        return None
    _, points, focal, calibration = min(fits, key=lambda fit: fit[0])
    # The demo starts with the same dark-clothed player visible at one end of
    # each view. This appearance heuristic resolves the 180-degree table ambiguity;
    # it is an initialization, not a person identity model.
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    ih, iw = gray.shape
    def actor_evidence(end):
        x, y = end.mean(axis=0)*[iw/w, ih/h]
        x0, x1 = max(0, int(x-.13*iw)), min(iw, int(x+.13*iw))
        y0, y1 = max(0, int(y-.35*ih)), min(ih, int(y-.04*ih))
        patch = ((gray < 90) & (hsv[:, :, 1] < 80))[y0:y1, x0:x1]
        return float(patch.mean()) if patch.size else 0
    if actor_evidence(points[[0, 3]]) < actor_evidence(points[[1, 2]]):
        points = np.roll(points, 2, axis=0)
    ends = np.array([points[[0, 3]].mean(0), points[[1, 2]].mean(0)])
    regions = []
    for pid, end in enumerate(ends):
        center = end+.12*(end-ends[1-pid])
        edge = points[[0, 3] if pid == 0 else [1, 2]]
        half_width = max(.13*w, .5*np.linalg.norm(edge[1]-edge[0]))
        regions.append([max(0, int(center[0]-half_width)), max(0, int(end[1]-.4*h)),
                        min(w, int(center[0]+half_width)), min(h, int(end[1]+.32*h))])
    return dict(corners=points.tolist(), focal_px=focal, calibration_mode='automatic_demo',
                player_rois_px=regions,
                method='Image line segments + tabletop color and boundary segmentation; demo appearance end ordering',
                **evidence, calibration=calibration, estimated=True)
