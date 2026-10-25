# Devpost video: voiceover script (2:48, with the team's four clips)

The cut (`trophy-demo-v2.mp4`) keeps all four of the team's clips (43 s) and trims the app scenes around them.
- **Placeholders:** the clips' slots are orange placeholders of exactly the right length. Drop each clip over its placeholder (same start and length) and the timing below holds.
- **No audio:** the app scenes have none (recorded headless), so the voiceover goes over them.
- **Clips 1 and 2** keep their own audio.
- **Pace:** about 150 words a minute.

| Time | On screen | Say |
|---|---|---|
| 0:00 | **Your clip 1** (7 s): Mu and Vedansh argue let / not let | *(their own audio)* |
| 0:07 | **Your clip 2** (10 s): Mu is Team USA ranked | *(you, on camera)* |
| 0:17 | Title card | "So we built Trophy: an AI referee for pickup games." |
| 0:20 | How it works | "Every phone becomes a camera. A Mac tracks the ball and runs the rules, and SpacetimeDB keeps every phone and every call in one live world state." |
| 0:29 | Join | "Scan the code, type a name, and you're a camera." |
| 0:33 | Go live, two phones | "For this demo we replay our own recordings as if they were live. Both phones start their angle on one schedule from SpacetimeDB, within a few milliseconds of each other." |
| 0:46 | Dashboard | "The laptop sees the same world state: every angle, every camera, and where each one saw the ball." |
| 0:53 | Calls | "Every call beeps and is read out by Cartesia, including whose fault it was." |
| 1:01 | **Your clip 3** (13 s): serve pose analysis | "It judges serves too. Here, Mu Du's toss stays under the six-inch minimum, and his toss leans more than thirty degrees off vertical: an illegal serve." |
| 1:14 | Angle switch | "Switch angles with one tap; it stays in sync." |
| 1:20 | Network sheet | "Every phone reports its drift back to Spacetime, so everyone sees the whole network live." |
| 1:26 | Challenge | "Still not sure? Tap Challenge, or just say it. Every phone opens the replay, the geometry is re-checked, Claude gives a second opinion, and the verdict and the reason are read out loud." |
| 1:39 | **Your clip 4** (13 s): the let in 3D | "And for the closest calls, we rebuild the play in 3D from both angles. There it is: the ball clips the net. A let." |
| 1:52 | Droid: house rule | "So let's make that a house rule. Just say it." |
| 1:57 | Droid working (sped up) | "A Factory Droid writes the rule in a locked-down sandbox. It can only touch the rule file and run the tests, and every step streams live to the phones." |
| 2:07 | Droid decides | "Tests pass, so the Droid decides. It applies the rule, re-judges our earlier plays, and shows exactly which calls changed." |
| 2:19 | Undo | "One tap undoes it." |
| 2:24 | Pickleball | "And it's not just ping pong. Pickleball, with rules the Droid wrote itself," |
| 2:32 | Volleyball | "volleyball," |
| 2:37 | Basketball | "and basketball: same phones, same referee." |
| 2:43 | Outro | "Trophy. Built at Cal Hacks with SpacetimeDB, Factory Droid, Cartesia and Claude." |

## Keep it honest (judges may ask)
- **The live app path:** replayed recordings (said at 0:33), real ball tracking on our own two-phone footage, and calls capped at "challengeable". That footage is unlabelled, so there's no accuracy number.
- **Clips 3 and 4** come from our recorded-footage analysis (`spikes/serve-analysis`: pose and 3D ball reconstruction), not from the live phone loop. Say "we analysed" or "we rebuild"; don't say "the phone shows this live". Its 3D path and pose numbers are estimates.
- **Other sports:** calls come from hand-marked events run through the rules the Droid wrote.
- **Claude's vote** is a second opinion blended with geometry, labelled uncalibrated.
