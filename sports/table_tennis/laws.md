# Laws of table tennis, paraphrased for the rule compiler

Source: the ITTF Handbook, chapter 2 "The Laws of Table Tennis" (the 2026 edition as mirrored by Table Tennis
England's "Laws of Table Tennis 2026-27"); clause numbers are the ITTF's. This file is a **paraphrase written by the
Trophy team on 2026-10-24**, not the official text, and it covers only what a camera referee can be asked about.
The 30 degree toss criterion under 2.6.2 is the ITTF review-system criterion, not law text (D-31). Ids below are
what `rule_ref` should cite.

## ittf:2.1 The table
- 2.1.1 The playing surface is 2.74 m long and 1.525 m wide, horizontal, 76 cm above the floor.
- 2.1.2 The playing surface includes the top edges of the table but not the vertical sides below them. A ball that
  hits the top edge is in; a ball that hits the vertical side face is not on the playing surface.
- 2.1.3 The surface is divided into two equal courts by a vertical net parallel to the end lines; each court
  belongs to one player (side A, side B). Doubles centre lines are part of each right half-court.

## ittf:2.3 The net assembly
- 2.3.1 The net assembly is the net, its suspension and the posts/clamps. 2.3.3 The top of the net is 15.25 cm
  above the playing surface along its whole length.

## ittf:2.5 Definitions
- 2.5.1 A rally is the period during which the ball is in play.
- 2.5.2 The ball is in play from the last moment it is stationary on the palm before being projected in service
  until the rally is decided as a let or a point.
- 2.5.3 A let is a rally whose result is not scored. 2.5.4 A point is a rally whose result is scored.
- 2.5.8 A player strikes the ball if they touch it in play with the racket held in the hand, or with the racket
  hand below the wrist.
- 2.5.9 A player obstructs the ball if they, or anything they wear or carry, touch the ball in play when it is
  above or travelling towards the playing surface, not having touched their court since last being struck by the
  opponent.
- 2.5.10/2.5.11 The server strikes the ball first in a rally; the receiver strikes it second.
- 2.5.14 The ball "passes over or around the net assembly" if it passes anywhere other than between the net and the
  net post or between the net and the playing surface.
- 2.5.15 The end line is taken to extend indefinitely in both directions.

## ittf:2.6 The service
- 2.6.1 Service starts with the ball resting freely on the open palm of the server's stationary free hand.
- 2.6.2 The server projects the ball near vertically upwards, without spin, so that it rises at least 16 cm after
  leaving the palm and then falls without touching anything before being struck. (Review criterion, not law text:
  a toss more than 30 degrees from vertical on the way up is treated as not "near vertical".)
- 2.6.3 As the ball falls the server strikes it so that it touches first the server's own court and then, after
  passing over or around the net assembly, touches the receiver's court (in doubles, the right half-courts in turn).
- 2.6.4 From the start of service until it is struck, the ball is above the level of the playing surface and behind
  the server's end line, and it is not hidden from the receiver by the server, their doubles partner or anything
  they wear or carry.
- 2.6.5 As soon as the ball has been projected, the server's free arm and hand are removed from the space between
  the ball and the net.
- 2.6.6 The server must serve so that the umpire can see that the law is obeyed. 2.6.6.1 Doubtful service: a
  warning the first time, a point to the receiver thereafter. 2.6.6.2 A clearly illegal service is a point to the
  receiver without warning.

## ittf:2.7 The return
- 2.7.1 After the ball has been served or returned, it must be struck so that it passes over or around the net
  assembly and touches the opponent's court, either directly or after touching the net assembly.

## ittf:2.8 The order of play
- 2.8.1 In singles the server makes a service, the receiver makes a return, and thereafter server and receiver
  alternately make returns.

## ittf:2.9 A let
- 2.9.1 The rally is a let: 2.9.1.1 if in service the ball touches the net assembly while passing over or around
  it, provided the service is otherwise correct (it lands on the receiver's court) or the ball is obstructed by the
  receiver; 2.9.1.2 if the service is delivered when the receiving side is not ready, provided they did not attempt
  to strike the ball; 2.9.1.3 if failure to make a correct service or return is due to a disturbance outside the
  players' control; 2.9.1.4 if play is interrupted by the umpire.
- A let replays the rally with the same server; nothing is scored.

## ittf:2.10 A point
- 2.10.1 Unless the rally is a let, a player scores a point:
  - 2.10.1.1 if the opponent fails to make a correct service;
  - 2.10.1.2 if the opponent fails to make a correct return;
  - 2.10.1.3 if, after the player has made a service or a return, the ball touches anything other than the net
    assembly before being struck by the opponent (this is the "double bounce": the ball bounces a second time on
    the opponent's court, or hits the floor, before the opponent strikes it);
  - 2.10.1.4 if the ball passes over the player's court or beyond their end line without touching their court,
    after being struck by the opponent (the opponent's shot went long or wide);
  - 2.10.1.5 if the ball, after being struck by the opponent, passes through the net or between the net and the
    post or between the net and the playing surface;
  - 2.10.1.6 if the opponent obstructs the ball;
  - 2.10.1.7 if the opponent deliberately strikes the ball twice in succession;
  - 2.10.1.9 if the opponent, or anything they wear or carry, moves the playing surface;
  - 2.10.1.10 if the opponent, or anything they wear or carry, touches the net assembly;
  - 2.10.1.11 if the opponent's free hand touches the playing surface;
  - 2.10.1.12 in doubles, if an opponent strikes out of the proper sequence.
- A shot that hits the net and drops back on the striker's own side never reaches the opponent's court: the
  striker failed to make a correct return (2.7.1, 2.10.1.2).

## ittf:2.11 A game
- 2.11.1 A game is won by the player first scoring 11 points unless both have scored 10, when the game is won by
  the first player to gain a lead of 2 points.

## ittf:2.12 A match
- 2.12.1 A match is the best of any odd number of games.

## ittf:2.13 The order of serving, receiving and ends
- 2.13.1 The right to choose the initial order of serving, receiving and ends is decided by lot.
- 2.13.3 After each 2 points have been scored the receiving player becomes the server, and so on until the end of
  the game, unless both players have scored 10 points or the expedite system is in operation, when the sequence
  stays the same but each player serves for only 1 point in turn.
- 2.13.6 The player who served first in a game receives first in the next game; players change ends after each
  game and, in the deciding game, when one player first scores 5 points.

## ittf:2.15 The expedite system
- 2.15.1 Expedite applies after 10 minutes of play in a game (unless 18 points have been scored); then each player
  serves one point in turn and a receiver who makes 13 successive correct returns wins the point. Out of scope for
  Trophy's referee.
