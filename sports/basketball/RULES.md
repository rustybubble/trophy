# Basketball (half-court pickup): the rules Trophy's calls rely on

A short summary in our own words for the Factory Droid, which writes `rules.yaml` from it. Article numbers refer to the
FIBA Official Basketball Rules 2024. NBA Rule 5 (scoring) and Rule 8 (out of bounds) agree on these points. Pickup
scoring is a common streetball convention with no official rulebook; what we observed in the clip is stated as observed.

## Court (Article 2)
- The three-point line is an arc 6.75 m from the point on the floor under the centre of the ring (6.60 m along the
  corners). The line itself is not part of the three-point area: a shooter with a foot on the line is inside the arc.
- The ring is 3.05 m above the floor. The field frame is in `config.yaml`.

## Goals and their value (Article 16)
- A goal is scored when a live ball enters the basket from above and stays in it or passes through.
- In regulation, a field goal is worth 2 points, or 3 if released from the three-point area. The shooter's position at
  release decides it (the last floor contact before a jump shot), not where the ball lands.
- **Pickup scoring in this clip ("1s and 2s"):** the clip's own overlay goes up by 1 for baskets inside the arc and by
  2 for baskets beyond it, to 11. Trophy's pack should score `points: 1` (inside) and `points: 2` (beyond the arc), and
  keep `attempt_points_hint` as the regulation 2/3 value.

## Out of bounds (Article 23)
- The ball is out when it touches a player who is out of bounds (touching the line or the floor beyond it), touches
  anything outside the court, or touches the backboard supports or the back of the backboard.
- The team whose player last touched the ball before it went out loses possession. In the half-court game play
  restarts with a check at the top of the key.

## Pickup conventions (not FIBA)
- Half court, 5 v 5 or fewer. Games to 11 by 1s and 2s, and the ball is checked at the top after each make.
- Fouls are called by the fouled player ("call your own"), so Trophy treats contact as a `foul_flag` capped at BETA
  (D-17) and never decides it alone.

## What the annotated clip exercises
`evals/fixtures/annotated/basketball/halfcourt-game2.*`: six made baskets in game (session) 2. There are four 1-point
baskets (inside the arc) and two 2-point baskets (beyond the arc): one by team B from the right wing and one by team A
from the top of the key. The score goes from A 0–1 B to A 4–5 B. Teams A and B are named as in the clip's overlay.
Made and points come from that overlay. Release positions are estimated by eye from one far camera. The 75 s window
contains no clear out-of-bounds play, so that rule is not exercised.
