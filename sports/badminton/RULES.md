# Badminton: the rulebook summary the Droid reads (interpreter job, D-43)

A short paraphrase of the BWF Laws of Badminton for pickup doubles/singles, with the law numbers to cite. It is a
summary written for Trophy, not the official text.

## Scoring (Law 7)
- Rally scoring: every rally scores a point for the side that wins it.
- A game is won at 21 with a 2-point lead; at 29-all the side reaching 30 wins.

## Faults (Law 13): the rally ends, the other side scores
- The shuttle lands outside the boundary lines (a shuttle on a line is in).
- The shuttle fails to pass over the net, or passes through or under it.
- The shuttle touches a player, the ceiling or anything outside the court.
- A player touches the net, or reaches over it before the shuttle crosses (except a follow-through after a legal hit).
- The same player hits the shuttle twice in a row, or both partners hit it in succession.

## Lets (Law 14): the rally is replayed, nobody scores
- The shuttle is caught in the net, or stays on top of it, after passing over the net (except on the service).
- During service, the receiver and server both commit a fault at once; or the server serves before the receiver is
  ready.
- An unforeseen or accidental disturbance.
- Note: a serve that clips the net and carries on into the correct service court is **legal** (not a let, unlike
  table tennis).

## A rally ends with a point when (Law 13, 7)
- The shuttle lands in on a side's court: the other side wins the rally.
- The shuttle lands out: the side that hit it loses the rally.

## Who is at fault
- Out, into the net, a double hit, a net touch: the side that committed it.
- A shuttle landing in: the side on whose court it landed.
- A let: nobody.

## What Trophy's annotated events carry
- `contact` (side, kind racket): a hit, by the side that hit.
- `bounce` (surface court, side = the half it landed in, `p_in` = 1 in, 0 out): the shuttle reaching the floor.
- `net` (kind into = did not pass, touch = touched the tape, from_side = the hitter, serve = on the service).
- `ball_dead` (reason stopped): play stopped (e.g. the shuttle stuck on the net).
