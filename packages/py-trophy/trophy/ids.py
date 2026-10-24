"""Identifiers (interfaces-v1 §1)."""

from __future__ import annotations

import re
import secrets

from ulid import ULID

# Crockford base32, lowercase (no i, l, o, u).
CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz"
_C = "[0-9a-hjkmnp-tv-z]"

GAME_ID_RE = re.compile(rf"^g_{_C}{{8}}$")
CAM_ID_RE = re.compile(rf"^c_{_C}{{6}}$")
PLAYER_ID_RE = re.compile(rf"^p_{_C}{{6}}$")
ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def _b32(n: int) -> str:
    return "".join(secrets.choice(CROCKFORD) for _ in range(n))


def new_game_id() -> str:
    return "g_" + _b32(8)


def new_cam_id() -> str:
    return "c_" + _b32(6)


def new_player_id() -> str:
    return "p_" + _b32(6)


def new_join_key() -> str:
    """22-char URL-safe random string (128 bit)."""
    return secrets.token_urlsafe(16)


def new_ulid() -> str:
    """event_id, call_id, challenge_id, req_id, rule_version."""
    return str(ULID())


def is_game_id(s: str) -> bool:
    return bool(GAME_ID_RE.match(s))


def is_cam_id(s: str) -> bool:
    return bool(CAM_ID_RE.match(s))


def is_ulid(s: str) -> bool:
    return bool(ULID_RE.match(s))
