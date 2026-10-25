"""replay_test: the Droid's test gate. Replays layer-1 logs through a sport module and checks the layer-2 events."""

from .checks import ReplayResult, run_replay

__all__ = ["ReplayResult", "run_replay"]
