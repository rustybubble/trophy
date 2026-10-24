# Rules compliance and prior-work disclosure

## Cal Hacks 13.0 rules that matter
- **All implementation must happen during the event**; projects started before the hackathon aren't allowed (ideation beforehand is fine).
- Team of 2–4; submit by **Sun Oct 25, 9:00 AM PT**; on site by 8:00 AM.
- Include an image, a GitHub repo and a live or recorded demo. Judging is a 3-minute pitch plus 2 minutes of Q&A.

## What existed before the event
| Item | What | How we use it |
|---|---|---|
| `courtcam` (MIT), https://github.com/subatomic-hamster/courtcam | A teammate's published computer-vision library (calibration, teams, make/miss, sport profiles, eval tools) | **A pinned dependency**, used through `services/courtcam-adapter`. **Disclosed on Devpost.** Confirm with organizers in #ask-directors |
| `subatomic-hamster/replay` (MIT) | The same teammate's Amazon Developer Hackathon entry | **Reference only.** We read its design docs; **no code is copied.** Its features are rebuilt here as Trophy Watch |
| Planning docs in `docs/plan`, `docs/research` | Pre-event research and plans (ideation) | Allowed: ideation |

## Footage
- Only CC BY / CC0 clips appear in the Devpost video; credits are in `data/clips/credits.json`.
- Research datasets (CalTennis, PadelVic, OpenTTGames) are for the live judged demo only.
- No footage in git. Never use Replay's private footage or clips with minors.
