# Pickleball: the rules Trophy's calls rely on

A short summary in our own words for the Factory Droid, which writes `rules.yaml` from it. Section numbers refer to
the USA Pickleball Official Rulebook (2025 edition); check sub-rule numbers against the edition in force before quoting
them, since they move between editions.

## Court and lines (Section 2)
- The doubles court is 20 ft × 44 ft (6.10 m × 13.41 m). The net is 36 in high at the sidelines and 34 in at the centre.
- The non-volley zone ("kitchen") is the 7 ft (2.13 m) area on each side of the net. Its lines, including the
  non-volley-zone line, are part of the zone.
- Field frame and line coordinates are in `config.yaml`.

## In and out (Section 6, line calls)
- A ball that lands on any line is in, except that a serve landing on the non-volley-zone line is short (a fault).
- A ball that first lands outside the baseline or sideline is out. It is a fault on the team that hit it.
- Calls go to the team on whose side the ball landed. If that team can't see it clearly, the ball is in. Trophy reports
  p_in with the call; a ball with p_in between the thresholds goes to PLAYERS DECIDE.

## Faults that end a rally (Section 7)
A fault is called on the team that:
- hits the ball into the net, or the ball doesn't clear the net (it lands back on the hitter's own side);
- hits the ball out;
- lets the ball bounce twice on its side before returning it (the rally is lost when the ball isn't returned);
- volleys before the two-bounce rule allows it (the serve and the return of serve must each bounce once);
- commits a non-volley-zone fault (below).
A ball that touches the net and still lands in the correct court is in play (the serve included; there are no service lets).

## Non-volley-zone faults (Section 9)
- A player may not volley (hit before the bounce) while touching the kitchen or its line.
- It is also a fault if, after a volley, the momentum of the volley carries the player, or anything they wear or carry,
  into the zone, even after the ball is dead.
- Players may stand in the kitchen at any other time and may play a ball that has bounced there.

## Scoring (Section 4)
- Traditional doubles scoring: only the serving team scores. Games to 11, win by 2.
- Each team has two servers per side out, except the team that starts the game, which gets one ("0-0-2").
- A fault by the serving team passes the serve to the second server, or to the other team (side out). A fault by the
  receiving team gives the serving team a point.

## What the annotated clips exercise
- `evals/fixtures/annotated/pickleball/mixer-sideline.*` (the judging-demo clip, SportsAlgo "Ultimate Mixer" doubles,
  CC BY): one close line call. A deep cross-court drive by the far team (B) lands just outside the near court's left
  sideline: `bounce` with `side: "A"` (the half of the field it landed in), `in: false`, `line: "sideline_left"`,
  `margin_m: -0.09`, `sigma_m: 0.12`, `p_in: 0.23`. It is a fault on the hitter, B (`opponent(ev.side)`), and the call
  goes to A. The call's confidence must come from the measurement (`p = 1 - p_in`, about 0.77), so a close ball is
  BETA (challengeable), never AUTO. The server and score are not visible in this video, so only the call is labelled.
- `evals/fixtures/annotated/pickleball/rec-doubles.*` (BT Pickleball, CC BY): three net faults (two by the near team as
  the serving team's opponents, one by the far team as server) and one ball not returned before the second bounce.
  Team A is the near team and team B the far team, which serves first.
- No clip has a clear kitchen (non-volley-zone) fault, so that rule is present but not exercised.
