# Devpost video: voiceover script (2:48)

The cut was recorded from the live stack: two phones at iPhone 15 Pro size plus the laptop dashboard. Its scene timeline is below.
- **No audio** is captured (headless browser), so record the voiceover over it.
- **Pace:** about 150 words a minute. Each line fits its scene at that pace; a block that runs short is fine, because the captions carry it.
- **Optional:** for the spoken calls, capture one call's beep and voice with an iPhone screen recording (sound on), and duck it under the voiceover at 0:46 and 1:07.

| Time | Scene (on screen) | Say |
|---|---|---|
| 0:00 | Title card | "This is Trophy: an AI referee for pickup games." |
| 0:05 | How it works | "Every phone becomes a camera. A Mac tracks the ball and runs the rules, and SpacetimeDB keeps every phone, every camera and every call in one shared, live world state." |
| 0:16 | Join | "Players scan a QR code, type a name, and their phone joins the game as a camera angle." |
| 0:22 | Go live, two phones | "For this demo we replay our own recordings as if they were live. Hit Go live: both phones count down and start their angle on the same schedule, read from SpacetimeDB. They stay within a few milliseconds of each other." |
| 0:38 | Dashboard | "The laptop sees the same world state: every angle, the frames each camera feeds the referee, and where each camera last saw the ball." |
| 0:46 | Calls | "When the referee makes a call, every phone beeps, and Cartesia reads it out, including whose fault it was." |
| 0:54 | Angle switch | "Any phone can switch angles with one tap, and it stays in sync." |
| 1:00 | Network sheet | "Each phone reports its drift back to Spacetime, so everyone sees the whole network live." |
| 1:06 | Challenge | "Think the call is wrong? Tap Challenge, or just say it. Every phone opens the instant replay. The geometry is re-checked, Claude gives a second opinion, and the verdict and the reason are read out loud." |
| 1:19 | Droid: new house rule | "Want a house rule? Just say it. Here: a ball that clips the net and lands in is a let." |
| 1:26 | Droid working (sped up) | "A Factory Droid picks it up from a Spacetime trigger and writes the rule in a locked-down sandbox. It can only edit the rule file and run the tests, and its plan and every step stream live to the phones." |
| 1:42 | Droid decides | "The tests pass, so the Droid decides. It applies the rule, re-judges the plays we already made, and shows exactly which calls changed, with the diff and the test results right there." |
| 1:57 | Undo | "Changed your mind? One tap undoes it, and the old calls come back." |
| 2:05 | Pickleball | "And it's not just ping pong. Here's pickleball from a Creative Commons clip. The Droid wrote this sport's let, out and fault rules itself, and tested them against hand-marked plays." |
| 2:18 | Volleyball | "Volleyball: same phones, same referee, a different rulebook." |
| 2:30 | Basketball | "And basketball. Every call is still spoken, and still challengeable." |
| 2:41 | Outro | "Trophy. Built at Cal Hacks with SpacetimeDB, Factory Droid, Cartesia and Claude. Thanks for watching." |

## Keep it honest (judges may ask)
- **Replayed footage:** the footage is replayed recordings, and the video says so at 0:22. The ping-pong calls come from real ball tracking on our own two-phone recording. That footage is unlabelled, so don't quote an accuracy number.
- **Other sports:** their calls come from hand-marked events run through the rules the Droid wrote (captions say "hand-marked"). There's no perception for them yet.
- **Claude's vote** is a second opinion blended with geometry. Its confidence is uncalibrated, and the phone labels it that way.
