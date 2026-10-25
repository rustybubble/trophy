"""decide(): the AI second opinion (interfaces-v1 §15, D-23). Claude, Gemini and Bitdeer vote in parallel, each with a
4 s timeout, blended with geometry; probabilities are UNCALIBRATED until >= 60 labelled challenges exist."""

from .blend import blend
from .runner import BackgroundDecider, decide
from .voters import BitdeerVoter, ClaudeVoter, GeminiVoter, Voter, VoterConfigError

__all__ = [
    "BackgroundDecider",
    "BitdeerVoter",
    "ClaudeVoter",
    "GeminiVoter",
    "Voter",
    "VoterConfigError",
    "blend",
    "decide",
]
