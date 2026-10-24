# Trophy Watch: post-game web app (owner A + D)

**Stack:** Vite + React + strict TypeScript (+ Three.js/Spark where 3D is needed), SpacetimeDB TypeScript SDK. Built to `dist/` and served by Caddy.

## Responsibilities
- Opens from the recap link (AgentMail/QR) once processing finishes. Works in any browser (phone, laptop, TV browser); touch, mouse and keyboard controls. **Not a Fire TV app.**
- Features (rebuilt from Replay's design; build plan §5B):
  - follow a player;
  - moments browser + ★ best play;
  - condensed game + rally browser;
  - broadcast mode (score bug, captions, commentary, Trophy's calls);
  - replay angles (real + 2.5D virtual), 0.5× slow-mo;
  - plain-English play search (Moss);
  - stats panel + player card + coach cards;
  - "can't tell" review queue (feeds calibration);
  - clips: trim, share, 9:16 reels;
  - pickup scoring modes;
  - consented naming;
  - **watch party** (synced playback and reactions through SpacetimeDB).
