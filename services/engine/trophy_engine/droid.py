"""The engine's side of the Factory Droid (D-43): house rules the Droid decides, and sport interpreters it writes.

House rules. ``submit_house_rule`` inserts a pending ``house_rule`` row (the compiler's trigger) carrying a snapshot of
the session for the Droid: the pack in force (``base_pack_path``, so rules stack) and every event so far
(``session_path``, the gate's baseline, so ``calls_changed`` is real). When the compiler reports the row ``ready`` with
a passing gate and the Droid's decision ``applies: true``, the engine applies it without a judge tap: it loads the file
at the gated commit only, re-judges the session's plays under the new pack (a superseding call for every changed
outcome), recomputes the score, sets status ``applied`` with the decision and announces it. ``revert_house_rule`` (one
tap) restores the previous pack and calls; ``reject_house_rule`` is the judge's veto before it applies;
``approve_house_rule`` stays as the judge's override for a ready row the Droid did not decide.

Interpreters. A game whose sport has no approved interpreter (no rules.yaml: an annotated sport, D-44) asks for one
when it starts (``request_droid_run``, an event trigger); ``regenerate_interpreter`` asks again (a judge's action).
The compiler watches queued ``droid_run`` rows. A ready, passing run is loaded from its gated commit, the session is
re-judged under it, and it is promoted to ``data/local/modules/<sport>/v<n>`` for later games.

The engine learns about results by polling Spacetime (``poll_droid``, from a background thread in the live loop);
results are applied on the loop thread through ``inbox`` + ``drain()``.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from trophy.ids import new_ulid

from .rejudge import change_rows, describe, rally_changes, replay_session, write_session
from .rules.cel import CelError, compile_rules
from .scoring import ScoringParams
from .sportmod.loader import LoadError, validate_against

if TYPE_CHECKING:
    from .engine import GameState

log = logging.getLogger("trophy.engine")
OPEN_HR_STATUSES = ("pending", "compiling")
LIVE_CALL_STATUSES = ("final", "upheld")


def placeholder_pack(sport: str) -> dict[str, Any]:
    """A pack with no rules, for a game whose sport is still waiting for the Droid's interpreter."""
    return {
        "sport": sport,
        "family": "flight",
        "version": 0,
        "name": f"{sport} (waiting for the Droid's interpreter)",
        "teams": [{"team_id": "A", "name": "Team A"}, {"team_id": "B", "name": "Team B"}],
        "field": {"frame": "unknown until the interpreter is written", "landmarks": []},
        "scoring": {"template": "rally", "params": {}},
        "rules": [],
    }


def gated_file(pack_path: str) -> str:
    """`<repo>/<file>@<commit>` -> the file's text at that commit (`git show`), so an edit made in the sandbox after the
    gate passed can never be what gets applied. Raises ValueError without a commit or outside a git repository."""
    path_s, sep, commit = pack_path.rpartition("@")
    if not sep or not re.fullmatch(r"[0-9a-f]{7,40}", commit):
        raise ValueError(f"pack_path has no gated commit: {pack_path!r}")
    path = Path(path_s).resolve()
    top = subprocess.run(
        ["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=10
    )
    if top.returncode != 0:
        raise ValueError(f"not in a git repository: {path.parent}")
    repo = Path(top.stdout.strip()).resolve()
    rel = path.relative_to(repo).as_posix()
    out = subprocess.run(
        ["git", "-C", str(repo), "show", f"{commit}:{rel}"], capture_output=True, text=True, timeout=10
    )
    if out.returncode != 0:
        raise ValueError(f"{rel} is not in commit {commit}: {out.stderr.strip()[:200]}")
    return out.stdout


def load_gated_pack(pack_path: str, sport: str) -> tuple[dict[str, Any], str]:
    """The pack at the gated commit, validated and compiled. Raises ValueError/LoadError/CelError/YAMLError."""
    text = gated_file(pack_path)
    pack = yaml.safe_load(text)
    errs = validate_against("rules", pack)
    if errs:
        raise LoadError(errs)
    if pack.get("sport") != sport:
        raise ValueError(f"pack is for {pack.get('sport')!r}, not {sport!r}")
    compile_rules(pack)
    return pack, text


class DroidMixin:
    """House rules and interpreters for ``Engine`` (engine.py). Uses its state, games, inbox and helpers."""

    # ------------------------------------------------------------ interpreters: where they live

    def module_dir_for(self, sport: str) -> Path:
        """The newest approved interpreter (approved_dir/<sport>/v<n> with a rules.yaml), else sports/<sport>."""
        approved = getattr(self, "approved_dir", None)
        if approved is not None and (Path(approved) / sport).is_dir():
            vs = sorted(
                (int(d.name[1:]), d)
                for d in (Path(approved) / sport).iterdir()
                if re.fullmatch(r"v\d+", d.name) and (d / "rules.yaml").is_file() and (d / "config.yaml").is_file()
            )
            if vs:
                return vs[-1][1]
        return self.modules_dir / sport

    def record_session_event(self, ev: dict[str, Any]) -> None:
        """Every event of a live game, in arrival order (re-judged when a rule is applied; no cap)."""
        g = self.games.get(str(ev.get("game_id")))
        if g is not None and g.game["status"] == "live":
            g.session_events.append(ev)

    # ------------------------------------------------------------ interpreters: requests

    def request_interpreter(self, g: GameState, source: str, reason: str) -> str | None:
        """Queue a droid_run (kind interpreter) for the compiler. One open request per game."""
        if g.interpreter_run:
            return g.interpreter_run
        now = self.now_ms()
        sport = g.game["sport"]
        run = {
            "schema": "trophy.droid_run.v1",
            "run_id": new_ulid(),
            "game_id": g.game["game_id"],
            "sport": sport,
            "base_sport": None if sport == "table_tennis" else "table_tennis",
            "kind": "interpreter",
            "trigger": {"source": source, "text": reason[:200], "requested_by": "engine"},
            "status": "queued",
            "backend": "droid",
            "model": "",
            "attempt": 0,
            "max_attempts": 3,
            "plan_md": "",
            "steps": [],
            "diff": "",
            "results": None,
            "started_at_ms": now,
            "updated_at_ms": now,
        }
        try:
            self.state.request_droid_run(run)
        except Exception:  # noqa: BLE001 - without Spacetime there is no Droid; the game goes on without calls
            log.exception("request_droid_run failed")
            return None
        g.interpreter_run = run["run_id"]
        name = sport.replace("_", " ")
        self._info(g, f"The Droid is writing the {name} interpreter", speech=f"The Droid is writing the {name} rules.")
        return run["run_id"]

    def _ctl_regenerate_interpreter(self, g: GameState, a: dict[str, Any], _by: str | None) -> None:
        self.request_interpreter(g, "user", str(a.get("reason") or "Regenerate interpreter (judge)"))

    # ------------------------------------------------------------ polling (off the loop thread)

    def poll_droid(self) -> int:
        """Read back the rows the compiler writes and queue what changed for drain(). Returns the commands queued.
        Safe to call from a background thread: it only reads engine state and puts commands in the inbox."""
        n = 0
        for gid, g in list(self.games.items()):
            for rv, row in list(g.house_rules.items()):
                if row.get("status") not in (*OPEN_HR_STATUSES, "ready") or row.get("_handled"):
                    continue
                try:
                    fetched = self.state.get_house_rule(rv)
                except Exception:  # noqa: BLE001
                    log.exception("get_house_rule %s failed", rv)
                    continue
                if fetched and fetched.get("status") != row.get("_seen_status"):
                    row["_seen_status"] = fetched.get("status")
                    self.inbox.put({"cmd": "droid_house_rule", "game_id": gid, "args": {"row": fetched}})
                    n += 1
            if g.interpreter_run:
                try:
                    run = self.state.get_droid_run(g.interpreter_run)
                except Exception:  # noqa: BLE001
                    log.exception("get_droid_run %s failed", g.interpreter_run)
                    continue
                if run and run.get("status") in ("ready", "failed"):
                    self.inbox.put({"cmd": "droid_interpreter", "game_id": gid, "args": {"run": run}})
                    n += 1
        return n

    # ------------------------------------------------------------ house rules

    def _ctl_submit_house_rule(self, g: GameState, a: dict[str, Any], _by: str | None) -> None:
        now = self.now_ms()
        rv = new_ulid()
        row: dict[str, Any] = {
            "rule_version": rv,
            "game_id": g.game["game_id"],
            "sport": g.game["sport"],
            "text": a["text"],
            "source": a.get("source", "typed"),
            "status": "pending",
            "backend": "droid",
            "plan_md": "",
            "steps": [],
            "diff": "",
            "results": None,
            "pack_path": None,
            "error": None,
            "base_rule_version": g.rule_version,
            "created_at_ms": now,
            "updated_at_ms": now,
        }
        sessions = getattr(self, "sessions_dir", None)
        if sessions is not None:
            # the Droid's inputs: the pack in force (rules stack) and this session's events (the gate's baseline)
            d = Path(sessions) / g.game["game_id"] / "house_rules" / rv
            d.mkdir(parents=True, exist_ok=True)
            (d / "base.rules.yaml").write_text(g.pack_text, "utf8")
            write_session(
                d / "session.json",
                game=g.game,
                first_server=g.first_server,
                events=list(g.session_events),
                rule_version=g.rule_version,
                dead_after_point_s=self.dead_after_point_s,
                server_from_first_hit=self.server_from_first_hit,
            )
            row["base_pack_path"] = str(d / "base.rules.yaml")
            row["session_path"] = str(d / "session.json")
        if g.needs_interpreter:
            row.update(status="failed", error="no interpreter for this sport yet: the Droid is still writing it")
        g.house_rules[rv] = row
        self.state.insert_house_rule({**row, "status": "pending"} if row["status"] == "failed" else row)
        if row["status"] == "failed":
            self.state.set_house_rule_status({"rule_version": rv, "status": "failed", "error": row["error"]})

    def _ctl_droid_house_rule(self, g: GameState, a: dict[str, Any], _by: str | None) -> None:
        """Internal (poll_droid): the compiler's view of a house_rule row changed."""
        fetched = a["row"]
        rv = fetched["rule_version"]
        row = g.house_rules.get(rv)
        if row is None or row.get("_handled") or fetched.get("game_id") != g.game["game_id"]:
            return
        row.update({k: v for k, v in fetched.items() if not k.startswith("_")})
        if fetched.get("status") == "failed":
            row["_handled"] = True
            self._info(
                g,
                "House rule not added: the Droid's tests failed"[:80],
                speech="The Droid couldn't add that house rule.",
                rule_id="house_rule",
            )
        elif fetched.get("status") == "ready":
            self._house_rule_ready(g, row)

    def _house_rule_ready(self, g: GameState, row: dict[str, Any]) -> None:
        rv = row["rule_version"]
        dec = row.get("decision") or {}
        passed = bool((row.get("results") or {}).get("passed"))
        now = self.now_ms()
        if dec.get("applies") is False:
            row["_handled"] = True
            rationale = str(dec.get("rationale") or "")[:300]
            decision = {
                "applies": False,
                "rationale": rationale,
                "decided_by": "droid",
                "decided_at_ms": now,
                "rejudged_rallies": 0,
                "calls_changed": 0,
            }
            row["status"] = "rejected"
            self.state.set_house_rule_status({"rule_version": rv, "status": "rejected", "decision": decision})
            self._info(
                g,
                f"House rule not applied: {row.get('text', '')}"[:80],
                speech=f"House rule not applied. {rationale}",
                rule_id="house_rule",
            )
            return
        if dec.get("applies") is not True:
            return  # no decision (an older compiler): the row waits for the judge's approve or reject
        if not passed or not row.get("pack_path"):
            return
        if row.get("base_rule_version") and row["base_rule_version"] != g.rule_version:
            row["_handled"] = True
            row["status"] = "failed"
            err = "stale: another rule was applied while the Droid worked on this one; say it again"
            self.state.set_house_rule_status({"rule_version": rv, "status": "failed", "error": err})
            self._info(
                g, "House rule not applied: the pack changed meanwhile", speech="Please say that house rule again."
            )
            return
        self._apply_house_rule(g, row, decided_by="droid", rationale=str(dec.get("rationale") or ""))

    def _apply_house_rule(self, g: GameState, row: dict[str, Any], *, decided_by: str, rationale: str) -> None:
        rv = row["rule_version"]
        row["_handled"] = True
        try:
            pack, text = load_gated_pack(str(row["pack_path"]), g.game["sport"])
        except (OSError, yaml.YAMLError, LoadError, CelError, ValueError) as e:
            row["status"] = "failed"
            self.state.set_house_rule_status(
                {"rule_version": rv, "status": "failed", "error": f"hot-load failed: {e}"[:400]}
            )
            return
        entry = self._rejudge_and_install(g, pack, text, version=rv, kind="house_rule", label=str(row.get("text", "")))
        n = len(entry["changes"])
        decision = {
            "applies": True,
            "rationale": rationale[:600],
            "decided_by": decided_by,
            "rejudged_rallies": entry["rejudged_rallies"],
            "calls_changed": n,
            "decided_at_ms": self.now_ms(),
        }
        entry["decision"] = decision
        results = dict(row.get("results") or {})
        results["calls_changed"] = entry["changes"]  # what actually changed in this game (live call ids)
        results.setdefault("tests", [])
        row["status"] = "applied"
        self.state.set_house_rule_status(
            {
                "rule_version": rv,
                "status": "applied",
                "pack_path": str(row["pack_path"]),
                "decision": decision,
                "results": results,
            }
        )
        text_ = row.get("text", "")
        changed = f"{n} call{'s' if n != 1 else ''} changed"
        self._info(
            g,
            f"House rule applied: {text_}"[:80],
            speech=f"House rule applied: {text_}. {changed}.",
            rule_id="house_rule",
        )
        self._house_rule_moment(g, row)

    def _ctl_approve_house_rule(self, g: GameState, a: dict[str, Any], _by: str | None) -> None:
        """The judge's override for a ready row (e.g. the Droid gave no decision)."""
        rv = a["rule_version"]
        row = g.house_rules.get(rv) or {}
        fetch = getattr(self.state, "get_house_rule", None)
        if fetch is not None:
            fetched = fetch(rv)
            if fetched:
                row = {**row, **fetched}
                g.house_rules.setdefault(rv, row).update(fetched)
        # Only what the compiler gated counts (review blocker 7): never a pack_path from the command's args, only a
        # row the compiler marked ready, and the file as it was at the gated commit, not the sandbox's working tree.
        pack_path = row.get("pack_path")
        if row.get("status") != "ready" or not pack_path:
            self.state.set_house_rule_status(
                {
                    "rule_version": rv,
                    "status": "failed",
                    "error": f"not approvable: status {row.get('status')!r}, "
                    f"pack_path {'set' if pack_path else 'missing'} (the compiler must report ready)",
                }
            )
            return
        self._apply_house_rule(
            g, g.house_rules.setdefault(rv, row), decided_by="judge", rationale="approved by the judge"
        )

    def _ctl_reject_house_rule(self, g: GameState, a: dict[str, Any], _by: str | None) -> None:
        """The judge's veto, while the rule is not applied yet."""
        rv = a["rule_version"]
        row = g.house_rules.get(rv)
        if row is not None and row.get("status") not in (*OPEN_HR_STATUSES, "ready"):
            log.warning("reject_house_rule %s: already %s", rv, row.get("status"))
            return
        if row is not None:
            row.update(status="rejected", _handled=True)
        decision = {
            "applies": False,
            "rationale": "vetoed by the judge",
            "decided_by": "judge",
            "decided_at_ms": self.now_ms(),
        }
        self.state.set_house_rule_status({"rule_version": rv, "status": "rejected", "decision": decision})

    def _ctl_revert_house_rule(self, g: GameState, a: dict[str, Any], _by: str | None) -> None:
        """One tap: restore the pack and the calls from before this rule (and before any rule applied after it)."""
        rv = a["rule_version"]
        idx = next((i for i, e in enumerate(g.applied) if e["version"] == rv), None)
        if idx is None:
            log.warning("revert_house_rule %s: not an applied rule of %s", rv, g.game["game_id"])
            return
        undone = g.applied[idx:]
        del g.applied[idx:]
        restored = 0
        now = self.now_ms()
        for e in reversed(undone):
            for cid in e["posted"]:
                c = next((c for c in g.calls if c["id"] == cid), None)
                if c is not None and c["status"] != "voided":
                    c["status"] = "voided"
                    self.state.update_call_status(cid, "voided")
            for cid, status in e["superseded"]:
                c = next((c for c in g.calls if c["id"] == cid), None)
                if c is not None:
                    c["status"] = status
                    self.state.update_call_status(cid, status)
                    restored += 1
            self._install_pack(g, *e["prev"])
            if e["kind"] == "house_rule":
                row = g.house_rules.get(e["version"])
                if row is not None:
                    row["status"] = "reverted"
                dec = {
                    **(e.get("decision") or {"applies": True, "rationale": "", "decided_by": "droid"}),
                    "reverted_at_ms": now,
                }
                self.state.set_house_rule_status({"rule_version": e["version"], "status": "reverted", "decision": dec})
        self._recompute(g)
        text = (g.house_rules.get(rv) or {}).get("text", "")
        extra = f" and {len(undone) - 1} later rule(s)" if len(undone) > 1 else ""
        self._info(
            g,
            f"House rule undone: {text}"[:80],
            speech=f"House rule undone{extra}. {restored} call{'s' if restored != 1 else ''} restored.",
            rule_id="house_rule",
        )

    def _house_rule_moment(self, g: GameState, row: dict[str, Any]) -> None:
        m = {
            "moment_id": new_ulid(),
            "game_id": g.game["game_id"],
            "kind": "house_rule",
            "t_game_s": g.last_t_s,
            "t_start_s": g.last_t_s,
            "t_end_s": g.last_t_s,
            "label": f"House rule: {row.get('text', '')}"[:80],
            "team_id": None,
            "track_id": None,
            "call_id": None,
            "rally_no": g.rally_no or None,
            "score_after": g.score().display(*g.sides),
            "tags": ["house_rule"],
            "highlight_score": 0.0,
            "reasons": [],
            "is_best_play": False,
            "thumb_t_s": g.last_t_s,
        }
        g.moments[m["moment_id"]] = m
        self._post_game(self.state.upsert_moment, m)

    # ------------------------------------------------------------ interpreter results

    def _ctl_droid_interpreter(self, g: GameState, a: dict[str, Any], _by: str | None) -> None:
        """Internal (poll_droid): the interpreter run this game waits for finished."""
        run = a["run"]
        if run.get("run_id") != g.interpreter_run:
            return
        g.interpreter_run = None
        sport = g.game["sport"]
        name = sport.replace("_", " ")
        res = run.get("results") or {}
        if run.get("status") != "ready" or not res.get("passed") or not run.get("commit") or not run.get("workspace"):
            self._info(
                g,
                f"The Droid couldn't write the {name} interpreter"[:80],
                speech=f"The Droid couldn't write the {name} rules yet.",
            )
            return
        pack_path = f"{run['workspace']}/sports/{sport}/rules.yaml@{run['commit']}"
        try:
            pack, text = load_gated_pack(pack_path, sport)
        except (OSError, yaml.YAMLError, LoadError, CelError, ValueError) as e:
            log.warning("interpreter %s: load failed: %s", run["run_id"], e)
            self._info(g, f"The {name} interpreter failed to load", speech="The Droid's rules failed to load.")
            return
        entry = self._rejudge_and_install(
            g, pack, text, version=str(run["run_id"]), kind="interpreter", label=f"{name} interpreter"
        )
        g.needs_interpreter = False
        self._promote_interpreter(g, run, text, pack_path)
        n_tests = len(res.get("tests") or [])
        n = len(entry["changes"])
        self._info(
            g,
            f"Interpreter ready: {name} ({n_tests} checks passed)"[:80],
            speech=f"The {name} rules are ready. {n} call{'s' if n != 1 else ''} made from the replay so far.",
        )

    def _promote_interpreter(self, g: GameState, run: dict[str, Any], text: str, pack_path: str) -> None:
        """The gated rules.yaml becomes the sport's approved interpreter (approved_dir/<sport>/v<n>), the run is marked
        approved (approved by its gate: it reproduced every labelled call) and a sport_module row is written."""
        sport = g.game["sport"]
        approved = getattr(self, "approved_dir", None)
        path = ""
        version = 1
        if approved is not None:
            base = Path(approved) / sport
            base.mkdir(parents=True, exist_ok=True)
            version = 1 + max([int(d.name[1:]) for d in base.iterdir() if re.fullmatch(r"v\d+", d.name)] or [0])
            dest = base / f"v{version}"
            dest.mkdir()
            (dest / "rules.yaml").write_text(text, "utf8")
            src = g.module.path
            for f in ("config.yaml", "events.py", "RULES.md"):
                if (src / f).is_file():
                    shutil.copyfile(src / f, dest / f)
            path = str(dest)
        row = {
            "sport": sport,
            "version": version,
            "backend": "droid",
            "run_id": run["run_id"],
            "path": path or pack_path,
            "commit": run["commit"],
            "game_id": g.game["game_id"],
            "approved_at_ms": self.now_ms(),
            "approved_by": "gate",
        }
        if path:
            Path(path, "sport_module.json").write_text(json.dumps(row, indent=1) + "\n", "utf8")
        self._post_game(self.state.set_droid_run_status, {"run_id": run["run_id"], "status": "approved"})
        self._post_game(self.state.upsert_sport_module, row)

    # ------------------------------------------------------------ re-judging

    def _install_pack(
        self,
        g: GameState,
        pack: dict[str, Any],
        text: str,
        version: str,
        params: dict[str, Any],
        needs_interpreter: bool = False,
    ) -> None:
        g.pack, g.pack_text, g.rules, g.rule_version = pack, text, compile_rules(pack), version
        g.params = params
        g.scoring = ScoringParams.from_pack(pack, params)
        g.needs_interpreter = needs_interpreter
        g.game["pack_version"] = version
        self.state.upsert_game(g.game)

    def _replay(self, g: GameState, pack: dict[str, Any]):
        return replay_session(
            sport=g.game["sport"],
            pack=pack,
            events=list(g.session_events),
            module_dir=g.module.path,
            teams=g.game.get("teams"),
            params=g.params,
            first_server=g.first_server,
            dead_after_point_s=self.dead_after_point_s,
            server_from_first_hit=self.server_from_first_hit,
        )

    def _rejudge_and_install(
        self, g: GameState, pack: dict[str, Any], text: str, *, version: str, kind: str, label: str
    ) -> dict[str, Any]:
        """Re-judge the session's plays under ``pack``, post a superseding call for each changed outcome, install the
        pack and recompute the score. A play a person already ruled on (a challenge, an undo, a correction) keeps its
        ruling. Returns the applied entry (also pushed on g.applied for revert)."""
        base, cand = self._replay(g, g.pack), self._replay(g, pack)
        changes = rally_changes(base, cand) if not (base.error or cand.error) else []
        if base.error or cand.error:
            log.warning("re-judge skipped: %s", base.error or cand.error)
        prev = (g.pack, g.pack_text, g.rule_version, g.params, g.needs_interpreter)
        # the new pack's params win; the game's own (per-game overrides, variants) fill the rest
        params = {**g.params, **(pack.get("params") or {})}
        self._install_pack(g, pack, text, version, params)
        entry: dict[str, Any] = {
            "version": version,
            "kind": kind,
            "label": label,
            "prev": prev,
            "superseded": [],
            "posted": [],
            "changes": [],
            "skipped": 0,
            "rejudged_rallies": len({c.get("rally_no") for c in cand.calls if c.get("rally_no")}),
        }
        for ch in changes:
            before, after = ch["before"], ch["after"]
            live = self._live_call_for(g, before) if before else None
            if before is not None and live is None:
                entry["skipped"] += 1  # a person already ruled on this play (or it was never called live)
                continue
            new = self._superseding_call(g, after, live, version, label) if after else None
            if live is not None:
                entry["superseded"].append((live["id"], live["status"]))
                live["status"] = "overturned"
                self.state.update_call_status(live["id"], "overturned")
            if new is not None:
                g.calls.append(new)
                self.state.post_call(new)
                entry["posted"].append(new["id"])
            row = change_rows([ch])[0]
            row["call_id"] = (new or live or {}).get("id", row.get("call_id"))
            row["rally_no"] = int((live or new or {}).get("rally_no") or row["rally_no"])
            entry["changes"].append(row)
        g.applied.append(entry)
        self._recompute(g)
        log.info(
            json.dumps(
                {
                    "svc": "engine",
                    "msg": "rejudged",
                    "game_id": g.game["game_id"],
                    "kind": kind,
                    "version": version,
                    "changes": len(entry["changes"]),
                    "skipped": entry["skipped"],
                }
            )
        )
        return entry

    @staticmethod
    def _live_call_for(g: GameState, replayed: dict[str, Any]) -> dict[str, Any] | None:
        """The live call that the replay's call stands for: same rule, same triggering event, still in force."""
        ev = (replayed.get("event_ids") or [None])[0]
        for c in reversed(g.calls):
            if (
                c.get("rule_id") == replayed.get("rule_id")
                and (c.get("event_ids") or [None])[0] == ev
                and c.get("status") in LIVE_CALL_STATUSES
                and c.get("kind") != "info"
            ):
                return c
        return None

    def _superseding_call(
        self, g: GameState, replayed: dict[str, Any], live: dict[str, Any] | None, version: str, label: str
    ) -> dict[str, Any]:
        new = dict(replayed)
        new.update(
            {
                "id": new_ulid(),
                "game_id": g.game["game_id"],
                "rule_version": version,
                "status": "final",
                "created_at_ms": self.now_ms(),
                "text": f"Re-judged: {replayed.get('text', '')}"[:80],
                # one announcement covers the re-judged plays; the phones don't speak each one
                "speech": "",
                "cue": {"beep": "none", "flash": "none"},
                "why": f"re-judged under {label}; was {describe(live) if live else 'no call'}"[:140],
            }
        )
        new.pop("suggested", None)
        if live is not None:
            new["supersedes"] = live["id"]
            if live.get("rally_no"):
                new["rally_no"] = live["rally_no"]
        return new
