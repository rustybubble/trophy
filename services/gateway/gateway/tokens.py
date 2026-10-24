"""cam_token (interfaces-v1 §1): a compact HMAC-SHA256 token ``<b64url(json claims)>.<b64url(mac)>``.

Claims: ``{g: game_id, c: cam_id, r: role, exp: epoch_ms}``. Roles are comma-combinable from
``cam|display|judge``, plus ``service`` for internal callers (the engine fetching replay crops).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

CLIENT_ROLES = frozenset({"cam", "display", "judge"})
ALL_ROLES = CLIENT_ROLES | {"service"}


class TokenError(Exception):
    pass


@dataclass(frozen=True)
class Claims:
    game_id: str
    cam_id: str
    role: str
    exp_ms: float

    @property
    def roles(self) -> frozenset[str]:
        return frozenset(r.strip() for r in self.role.split(","))

    def has(self, role: str) -> bool:
        return role in self.roles


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def normalize_role(role: str, allowed: frozenset[str] = CLIENT_ROLES) -> str:
    roles = sorted({r.strip() for r in role.split(",") if r.strip()})
    if not roles or any(r not in allowed for r in roles):
        raise TokenError(f"role must be a comma list of {sorted(allowed)}")
    return ",".join(roles)


def mint(
    secret: str, game_id: str, cam_id: str, role: str, ttl_s: float, now_ms: float | None = None
) -> tuple[str, float]:
    exp = (now_ms if now_ms is not None else time.time() * 1000) + ttl_s * 1000
    body = _b64(json.dumps({"g": game_id, "c": cam_id, "r": role, "exp": exp}, separators=(",", ":")).encode())
    mac = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{mac}", exp


def verify(secret: str, token: str, now_ms: float | None = None) -> Claims:
    try:
        body, mac = token.split(".")
    except ValueError:
        raise TokenError("malformed token") from None
    want = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(want, mac):
        raise TokenError("bad signature")
    try:
        c = json.loads(_unb64(body))
        claims = Claims(game_id=c["g"], cam_id=c["c"], role=c["r"], exp_ms=float(c["exp"]))
    except (ValueError, KeyError, TypeError):
        raise TokenError("malformed claims") from None
    if claims.exp_ms < (now_ms if now_ms is not None else time.time() * 1000):
        raise TokenError("token expired")
    return claims


if __name__ == "__main__":  # python -m gateway.tokens service  -> a 30-day service token for internal callers
    import sys

    from .config import Settings

    s = Settings.from_env()
    tok, _ = mint(s.token_secret, "*", "svc", "service", 30 * 86400)
    sys.stdout.write(tok + "\n")
