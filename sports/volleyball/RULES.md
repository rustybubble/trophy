# Volleyball: the rules Trophy's calls rely on

A short summary in our own words for the Factory Droid, which writes `rules.yaml` from it. Rule numbers refer to the
FIVB Official Volleyball Rules 2025–2028; USA Volleyball's domestic rulebook follows the same structure for these
points. Check the numbering against the current edition before quoting it.

## Court (Rule 1)
- The court is 18 m × 9 m, split by the centre line under the net into two 9 m × 9 m halves. A 3 m attack line runs
  across each half.
- Boundary lines are 5 cm wide and belong to the court.

## In and out (Rule 8)
- **In (8.3):** the ball is in when it touches the floor of the playing court, boundary lines included.
- **Out (8.4):** the ball is out when it lands completely outside the boundary lines, touches an object outside the
  court (ceiling, wall, a person off court), touches the antennae or the net outside them, or crosses the net's vertical
  plane outside the crossing space.
- Who is at fault: when the ball lands in, the team on whose court it lands loses the rally. When it goes out, the team
  that touched it last loses the rally.

## Playing the ball (Rule 9)
- **Team hits (9.1):** a team has at most three hits (plus the block) to return the ball. The block doesn't count as a hit.
- **Four hits (9.3.1):** a fourth hit is a fault.
- **Double contact (9.3.3):** a player may not hit the ball twice in a row, except on the block or on the team's first
  hit when it's a single action.

## At the net (Rule 11)
- **Net contact (11.3):** touching the net between the antennae while playing the ball is a fault. Incidental contact
  that doesn't interfere is not.
- **Ball into the net:** a ball driven into the net may be played again if the team has hits left. If it falls dead on
  that side, the team that hit it loses the rally.
- **Reaching over (11.1):** players may not touch the ball in the opponent's space before or during the opponent's
  attack hit. A block that follows through after the opponent's attack is allowed.

## Scoring (Rule 6)
- Rally-point system (6.1): every rally scores one point, for the team that wins it. Sets go to 25, win by 2, and the
  fifth set to 15. The team that wins the rally serves next.

## What the annotated clips exercise
Team A is HND (near court) and team B is AZM (far court) in both; rally winners match the clip's own score overlay.
- `evals/fixtures/annotated/volleyball/sideline-ball.*` (the judging-demo clip): one close line call. The ball comes
  down on the near (HND) court's right sideline: `bounce` with `side: "A"`, `in: true`, `line: "side_right"`,
  `margin_m: 0.025`, `sigma_m: 0.05`, `p_in: 0.69`. A ball touching the line is in (8.3), so AZM wins the rally (the
  overlay agrees). The call's confidence must come from the measurement (`p = p_in` for an in call, `1 - p_in` for an
  out call), so this close ball is BETA, not AUTO.
- `evals/fixtures/annotated/volleyball/amateur-set.*`: four rallies. In three, the ball goes down in AZM's court (an
  attack that gets through, and a serve AZM touches into the floor). In one, an HND touch sends the ball away and isn't
  returned. Lines aren't resolvable in those rallies (`d_lines_m` empty) and the third rally is low confidence (0.5).
- No fixture has a ball landing out (`in: false`). If one does, the team that touched it last is at fault
  (`payload.last_touch_side` when present, otherwise the team that sent it over: `opponent(ev.side)`).
