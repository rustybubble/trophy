# Devpost video: voiceover script (`trophy-demo-v3.mp4`, 2:25)

**What changed from the original cut:**
- The title card and the angle-switch scene are gone.
- The Mac and CC BY are not mentioned.
- Captions are shorter.
- The challenge replays both angles on both phones.
- The sports clips are new, each with a close call.

The app scenes have no audio, so the voiceover goes over them. Speak at about 150 words a minute.

| Time | On screen | Say |
|---|---|---|
| 0:00 | How it works | "This is Trophy: an AI referee for pickup games. Every phone is a camera, and SpacetimeDB keeps every phone and every call in one live world state." |
| 0:09 | Join | "Scan a code, type your name, and your phone is a camera angle." |
| 0:14 | Go live, two phones | "Here we're replaying our own match as if it were live. Hit Go live, and both phones start their angle on the same schedule from SpacetimeDB, within a few milliseconds of each other." |
| 0:28 | Dashboard | "The dashboard reads the same world state: every angle and every phone, live." |
| 0:35 | Calls | "When the referee makes a call, every phone beeps, and Cartesia reads it out, including whose fault it was." |
| 0:47 | Network sheet | "Every phone reports its drift back to Spacetime, so everyone sees the whole network." |
| 0:54 | Challenge | "Disagree? Tap Challenge, or just say it. Every phone replays both angles, Claude gives a second opinion, and the verdict is read out loud." |
| 1:05 | Droid: house rule | "Want a house rule? Just say it: a ball that clips the net is a let." |
| 1:11 | Droid working (sped up) | "A Factory Droid writes the rule in a locked-down sandbox. It can only touch the rule file and run the tests, and every step streams live to the phones." |
| 1:27 | Droid decides | "The tests pass, so the Droid decides. It applies the rule, re-judges the game, and shows exactly which calls changed." |
| 1:40 | Undo | "And one tap undoes it." |
| 1:46 | Pickleball close call + challenge | "It handles close calls in any sport. Pickleball: out by inches? The referee says out, but it's only seventy-seven percent sure, so we challenge it, and it's reviewed on the spot." |
| 2:02 | Volleyball | "Volleyball: a ball right on the line, called in." |
| 2:11 | Basketball | "Basketball: a foot right on the three-point arc. It counts it, and tells you how unsure it is." |
| 2:20 | Outro | "Trophy. Built at Cal Hacks with SpacetimeDB, Factory Droid, Cartesia and Claude." |

## Notes
- **The 0:14 line** ("replaying our own match as if it were live") is the only place the video says the footage is replayed. You can cut it, but keep the demo setup in your Devpost text so nobody is misled.
- **The referee's location:** the video never mentions the laptop. The referee does run on a laptop server, so don't say "it all runs on the phones".
- **Other sports** use hand-marked events with the rules the Droid wrote.
- **Claude's confidence** is uncalibrated.
- **The cut with your four clips** has its own script in `VOICEOVER-with-your-clips.md`; that cut still has the older app scenes.
