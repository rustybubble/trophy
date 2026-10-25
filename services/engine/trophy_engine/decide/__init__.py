"""decide(): the AI second opinion (interfaces-v1 §15, D-23, D-41). Claude votes in the background with a 4 s timeout,
blended with geometry; probabilities are UNCALIBRATED until >= 60 labelled challenges exist."""

from .blend import blend
from .runner import BackgroundDecider, decide
from .voters import ClaudeVoter, Voter, VoterConfigError

__all__ = ["BackgroundDecider", "ClaudeVoter", "Voter", "VoterConfigError", "blend", "decide"]
