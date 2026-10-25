# Table tennis: the rulebook summary the Droid reads (interpreter job, D-43)

A short paraphrase of the ITTF Laws of Table Tennis (Handbook, section 2) for pickup play, with the law numbers to
cite. It is a summary written for Trophy, not the official text.

## Scoring (2.11, 2.12, 2.13)
- A game goes to 11 with a 2-point lead. Each player serves 2 points in turn; from 10-all, 1 each.

## The service (2.6)
- The ball rests on the open palm, is tossed near vertically, rises at least 16 cm (house rule here: more than 6 in),
  and is struck as it falls.
- The served ball bounces first on the server's court, then passes over the net and touches the receiver's court.

## Lets (2.9): the rally is replayed, nobody scores
- The served ball touches the net assembly and then lands correctly (or is obstructed by the receiver).
- Play is disturbed by something outside the players' control.

## A point (2.10): the opponent scores when a player
- fails to make a correct service or return;
- lets the ball bounce twice on their own court (the opponent wins the point);
- hits the ball so it misses the table, i.e. it lands on the floor (out), or into the net without crossing;
- volleys the ball, touches the net, moves the table, or hits the ball twice in succession.

## Edges (2.1.2, practice)
- The top edge of the table is part of the playing surface: an edge ball is good; the side face is not.

## Who is at fault
- Serve faults: the server. Out, net, double bounce on a side: the player who last had to play the ball. A let:
  nobody.

## What Trophy's events carry
- `bounce` (surface table|floor, side, p_in, edge probabilities near an edge), `contact` (racket hits), `net` (kind
  touch|into|over, from_side, serve), `ball_dead` (reason), `serve_toss` (height and angle with σ).
