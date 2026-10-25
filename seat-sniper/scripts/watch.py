#!/usr/bin/env python3
"""Remember class-seat checks and decide when the student needs to hear about a change.

Cubbie reads the school's class-search page and passes the seat count to this script. The watchlist keeps the
previous result, so an open seat triggers an alert without sending the same message at every check. It also
tracks replies and one-time call follow-ups. State lives under HOME (~/.config/seat-sniper), so it survives
sandbox restarts and Skill updates. This script uses only Python's standard library.

Commands: add, list, remove, check, ack, followup. The student gets a text first; followup says whether
to call when no reply came within 5 minutes. Run with --sample for an offline demo that leaves saved state alone.

Exit codes: 0 ok, 2 bad arguments, 4 unknown watch id.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_REALERT_MINUTES = 120
UNREADABLE_LIMIT = 3


def fail(message: str, code: int):
    print(message, file=sys.stderr)
    sys.exit(code)


def state_file(override: str | None) -> Path:
    if override:
        return Path(override)
    # Keep using the older Skills data location when it is already configured; otherwise use the usual
    # per-user config directory. That lets existing watchlists survive an upgrade.
    data_dir = os.environ.get("SKILL_DATA_DIR") or Path.home() / ".config" / "seat-sniper"
    return Path(data_dir) / "watchlist.json"


def load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            data.setdefault("next_id", 1)
            return data
    except (OSError, ValueError):
        pass
    return {"next_id": 1, "items": []}


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Replace the state file only after the new JSON is fully written, so an interrupted write is less
    # likely to leave the student's watchlist half-saved.
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(path)


def parse_now(text: str | None) -> datetime:
    """Parse the student's local time as ISO 8601; only the gaps between checks matter."""
    if not text:
        return datetime.now(timezone.utc)
    try:
        value = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        fail(f"--now must look like 2026-10-24T17:30:00 (got {text!r}).", 2)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def describe(item: dict) -> str:
    bits = [item["course"]]
    if item.get("section"):
        bits.append(f"section {item['section']}")
    if item.get("term"):
        bits.append(item["term"])
    return " ".join(bits[:1]) + (f" ({', '.join(bits[1:])})" if len(bits) > 1 else "")


def find(data: dict, item_id: int) -> dict:
    for item in data["items"]:
        if item["id"] == item_id:
            return item
    fail(f"No watch with id {item_id}. Run the list command to see ids.", 4)


def cmd_add(path: Path, args) -> int:
    data = load(path)
    for item in data["items"]:
        if (item["course"].lower(), item.get("section"), item.get("term")) == (
            args.course.lower(), args.section, args.term):
            print(f"EXISTS id={item['id']} {describe(item)}")
            return 0
    item = {
        "id": data["next_id"], "course": args.course.strip(), "section": args.section, "term": args.term,
        "url": args.url, "created": parse_now(args.now).isoformat(),
        "last_open": None, "last_alert": None, "last_check": None, "failures": 0, "alerts": 0,
        "call": not args.no_call, "acked": None, "called": None,
    }
    data["next_id"] += 1
    data["items"].append(item)
    save(path, data)
    print(f"ADDED id={item['id']} {describe(item)}")
    return 0


def cmd_list(path: Path, _args) -> int:
    data = load(path)
    if not data["items"]:
        print("EMPTY: nothing is being watched.")
        return 0
    for item in data["items"]:
        seen = "not checked yet" if item["last_open"] is None else (
            "full" if item["last_open"] == 0 else f"{item['last_open']} open")
        link = f" {item['url']}" if item.get("url") else ""
        print(f"id={item['id']} {describe(item)} - last seen: {seen}{link}")
    return 0


def cmd_remove(path: Path, args) -> int:
    data = load(path)
    item = find(data, args.id)
    data["items"].remove(item)
    save(path, data)
    print(f"REMOVED id={args.id} {describe(item)}")
    return 0


def cmd_ack(path: Path, args) -> int:
    """The student replied about an alert: stop reminders and the follow-up call for it."""
    data = load(path)
    item = find(data, args.id)
    item["acked"] = parse_now(args.now).isoformat()
    save(path, data)
    print(f"ACKED id={args.id} {describe(item)}")
    return 0


def cmd_followup(path: Path, args) -> int:
    """Run a few minutes after the alert text: say whether to call the student."""
    data = load(path)
    item = find(data, args.id)
    now, name = parse_now(args.now), describe(item)
    last_alert = item.get("last_alert")
    if not last_alert:
        print(f"SKIP: no open alert for {name}; the seat may have filled. Do not call.")
        return 0
    if not item.get("call", True):
        print(f"SKIP: calls are off for {name}.")
        return 0
    alerted = datetime.fromisoformat(last_alert)
    # A reply or an earlier call belongs to this alert only if it happened after the alert was sent.
    for field, text in (("acked", "the student already replied"), ("called", "the student was already called")):
        stamp = item.get(field)
        if stamp and datetime.fromisoformat(stamp) >= alerted:
            print(f"SKIP: {text} about {name}.")
            return 0
    waited = (now - alerted).total_seconds() / 60
    if waited < args.wait_minutes:
        print(f"SKIP: only {waited:.0f} minutes since the text; wait until {args.wait_minutes:g}.")
        return 0
    item["called"] = now.isoformat()
    save(path, data)
    print(f"CALL: {name} opened {waited:.0f} minutes ago and the student has not replied. Call them once.")
    return 0


def cmd_check(path: Path, args) -> int:
    if (args.open_seats is None) == (not args.unreadable):
        fail("Give exactly one of --open-seats N or --unreadable.", 2)
    data = load(path)
    item = find(data, args.id)
    now = parse_now(args.now)
    name = describe(item)
    item["last_check"] = now.isoformat()

    if args.unreadable:
        # A failed page read is not the same as zero seats. Keep the last known count intact and
        # only ask Cubbie to tell the student after several consecutive failures.
        item["failures"] = item.get("failures", 0) + 1
        save(path, data)
        if item["failures"] == UNREADABLE_LIMIT:
            print(f"TELL_STUDENT: could not read the class page {UNREADABLE_LIMIT} times in a row for {name}.")
        else:
            print(f"UNREADABLE: {name} (failed reads in a row: {item['failures']}).")
        return 0

    if args.open_seats < 0:
        fail("--open-seats cannot be negative.", 2)
    seats, previous = args.open_seats, item["last_open"]
    item["failures"] = 0
    item["last_open"] = seats
    waitlist = f", waitlist {args.waitlist}" if args.waitlist is not None else ""

    if seats == 0:
        # Clear the alert marker when the class fills again, so the next opening is a fresh alert.
        item["last_alert"] = None  # a later opening should alert again
        save(path, data)
        if previous:
            print(f"CLOSED_AGAIN: {name} filled back up{waitlist}. Do not text the student.")
        else:
            print(f"NO_CHANGE: {name} is still full{waitlist}.")
        return 0

    seat_word = "seat" if seats == 1 else "seats"
    if previous is None:
        message = f"ALERT: {name} has {seats} open {seat_word} right now{waitlist}."
    elif previous == 0:
        message = f"ALERT: {name} just opened up, {seats} open {seat_word}{waitlist}."
    else:
        last_alert = item.get("last_alert")
        acked = item.get("acked")
        # Once the student has replied, keep quiet about the same opening. A new opening after the
        # class fills will be treated as a separate alert.
        if acked and last_alert and datetime.fromisoformat(acked) >= datetime.fromisoformat(last_alert):
            save(path, data)
            print(f"NO_CHANGE: {name} is still open ({seats}), the student already replied.")
            return 0
        minutes = None
        if last_alert:
            minutes = (now - datetime.fromisoformat(last_alert)).total_seconds() / 60
        if minutes is not None and minutes < args.realert_minutes:
            save(path, data)
            print(f"NO_CHANGE: {name} is still open ({seats}), the student was already told.")
            return 0
        message = f"STILL_OPEN: {name} still has {seats} open {seat_word}{waitlist}. The student has not stopped the watch."
    item["last_alert"] = now.isoformat()
    item["alerts"] = item.get("alerts", 0) + 1
    save(path, data)
    print(message)
    return 0


def run_sample() -> int:
    """Walk through a made-up class filling and opening, in a throwaway folder."""
    with tempfile.TemporaryDirectory() as folder:
        state = str(Path(folder) / "watchlist.json")
        steps = [
            ["add", "--course", "DEMO 101", "--section", "11111", "--term", "Spring 2027", "--now", "2026-10-24T08:00:00"],
            ["check", "--id", "1", "--open-seats", "0", "--now", "2026-10-24T08:15:00"],
            ["check", "--id", "1", "--open-seats", "0", "--now", "2026-10-24T08:30:00"],
            ["check", "--id", "1", "--open-seats", "2", "--now", "2026-10-24T08:45:00"],
            ["followup", "--id", "1", "--now", "2026-10-24T08:47:00"],
            ["followup", "--id", "1", "--now", "2026-10-24T08:51:00"],
            ["followup", "--id", "1", "--now", "2026-10-24T08:52:00"],
            ["check", "--id", "1", "--open-seats", "2", "--now", "2026-10-24T09:00:00"],
            ["check", "--id", "1", "--open-seats", "1", "--now", "2026-10-24T10:50:00"],
            ["ack", "--id", "1", "--now", "2026-10-24T10:55:00"],
            ["check", "--id", "1", "--open-seats", "1", "--now", "2026-10-24T13:00:00"],
            ["check", "--id", "1", "--unreadable", "--now", "2026-10-24T13:15:00"],
            ["list"],
            ["remove", "--id", "1"],
        ]
        for step in steps:
            print(f"$ {' '.join(step)}")
            main(["--state", state, *step])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state", help="watchlist file to use instead of the saved one (for tests)")
    parser.add_argument("--sample", action="store_true", help="offline demo with made-up data; saved state is left alone")
    commands = parser.add_subparsers(dest="command")

    add = commands.add_parser("add", help="start watching a class")
    add.add_argument("--course", required=True, help="course code, for example 'CSE 355'")
    add.add_argument("--section", help="section or class number, if the student wants one section")
    add.add_argument("--term", help="term, for example 'Spring 2027'")
    add.add_argument("--url", help="class search link for this class")
    add.add_argument("--now", help="student's local time, ISO 8601")
    add.add_argument("--no-call", action="store_true", help="the student wants texts only, never a phone call")

    commands.add_parser("list", help="show everything being watched")

    ack = commands.add_parser("ack", help="the student replied about an alert")
    ack.add_argument("--id", type=int, required=True)
    ack.add_argument("--now", help="student's local time, ISO 8601")

    followup = commands.add_parser("followup", help="a few minutes after an alert: should Cubbie call?")
    followup.add_argument("--id", type=int, required=True)
    followup.add_argument("--now", help="student's local time, ISO 8601")
    followup.add_argument("--wait-minutes", type=float, default=5, help="minutes to wait for a reply before calling (default 5)")

    remove = commands.add_parser("remove", help="stop watching a class")
    remove.add_argument("--id", type=int, required=True)

    check = commands.add_parser("check", help="record what the class page showed and say what to do")
    check.add_argument("--id", type=int, required=True)
    check.add_argument("--open-seats", type=int, help="open seats read from the class page")
    check.add_argument("--waitlist", type=int, help="waitlist size, if the page shows one")
    check.add_argument("--unreadable", action="store_true", help="the class page could not be read this time")
    check.add_argument("--now", help="student's local time, ISO 8601")
    check.add_argument("--realert-minutes", type=int, default=DEFAULT_REALERT_MINUTES,
                       help="how long an open seat stays quiet before a reminder (default 120)")

    args = parser.parse_args(argv)
    if args.sample:
        return run_sample()
    if not args.command:
        parser.print_usage(sys.stderr)
        return 2
    path = state_file(args.state)
    handlers = {"add": cmd_add, "list": cmd_list, "remove": cmd_remove, "check": cmd_check,
                "ack": cmd_ack, "followup": cmd_followup}
    return handlers[args.command](path, args)


if __name__ == "__main__":
    sys.exit(main())
