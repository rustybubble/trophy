import numpy as np

from flight.detect import ClassicalDetector


def test_classical_detector_finds_moving_white_ball_on_static_scene():
    det = ClassicalDetector(colour="white", expected_radius_px=6)
    rng = np.random.default_rng(0)
    bg = np.full((720, 1280, 3), (40, 90, 30), np.uint8)
    import cv2

    cv2.rectangle(bg, (200, 300), (1080, 520), (120, 60, 20), -1)
    cv2.line(bg, (200, 300), (1080, 300), (255, 255, 255), 2)
    hits = 0
    for i in range(40):
        img = bg.copy()
        img = np.clip(img.astype(int) + rng.integers(-3, 4, img.shape), 0, 255).astype(np.uint8)
        cx, cy = 250 + 20 * i, 420 - 10 * i + 0.3 * i * i
        cv2.circle(img, (int(cx), int(cy)), 6, (250, 250, 250), -1)
        cands = det(img)
        if i >= 5 and cands and np.hypot(cands[0]["xy_px"][0] - cx, cands[0]["xy_px"][1] - cy) < 3:
            hits += 1
    assert hits >= 30
