"""The confidence gate (interfaces-v1 §10, D-4, D-17): tier is a ceiling, foul_flag <= BETA, untrusted calib <= BETA."""

from __future__ import annotations

AUTO_P = 0.90
BETA_P = 0.60
TIER_ORDER = {"AUTO": 2, "BETA": 1, "PLAYERS": 0}


def gate(p: float, rule_tier: str, kind: str, calib_untrusted: bool = False, sensed: bool = True) -> tuple[str, str]:
    """Return (tier, shown) for a call with probability ``p`` under a rule whose tier is a ceiling."""
    if not sensed:
        return "PLAYERS", "evidence"
    if p >= AUTO_P:
        tier, shown = "AUTO", "auto"
    elif p >= BETA_P:
        tier, shown = "BETA", "challengeable"
    else:
        tier, shown = "BETA", "replay"
    ceiling = rule_tier
    if kind == "foul_flag" or calib_untrusted:
        ceiling = "BETA" if TIER_ORDER.get(ceiling, 1) > TIER_ORDER["BETA"] else ceiling
    if TIER_ORDER.get(ceiling, 1) < TIER_ORDER[tier]:
        tier = ceiling
        shown = "challengeable" if tier == "BETA" and shown == "auto" else ("evidence" if tier == "PLAYERS" else shown)
    return tier, shown
