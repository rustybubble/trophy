"""p_final = w_geo * p_geometry + sum(w_i * p_i), normalised over the voters that answered."""

from __future__ import annotations

from typing import Any

W_GEOMETRY = 0.5
W_VOTERS = 0.5


def blend(options: list[str], p_geometry: dict[str, float] | None, votes: list[dict[str, Any]]) -> dict[str, Any]:
    answered = [v for v in votes if not v.get("error") and v.get("probs")]
    weights: dict[str, float] = {}
    p_final = dict.fromkeys(options, 0.0)
    total = 0.0
    if p_geometry:
        weights["geometry"] = W_GEOMETRY
        for o in options:
            p_final[o] += W_GEOMETRY * float(p_geometry.get(o, 0.0))
        total += W_GEOMETRY
    if answered:
        w = W_VOTERS / len(answered)
        for v in answered:
            weights[str(v["backend"])] = w
            for o in options:
                p_final[o] += w * float(v["probs"].get(o, 0.0))
            total += w
    if total <= 0:
        p_final = {o: 1.0 / len(options) for o in options}
    else:
        p_final = {o: round(p / total, 4) for o, p in p_final.items()}
    suggested = max(p_final.items(), key=lambda kv: kv[1])[0]
    return {
        "p_final": p_final,
        "suggested": suggested,
        "weights": weights,
        "calibrated": False,
        "p_source": "decide:ensemble",
    }
