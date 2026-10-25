#!/usr/bin/env python3
"""Make a semester-by-semester draft from a student's goals and remaining courses.

The input file is the planner's source of truth. It does not look up a catalog or fill in missing prerequisites,
offerings or difficulty scores. Given those details, it places courses around prerequisites, the student's pace,
summer and internship limits, then calls out terms worth reviewing. See references/planner.md for the input
format and how to turn a DARS report into course data. This script uses only Python's standard library.

Usage:  python3 scripts/plan.py --input plan_input.json [--json]
        python3 scripts/plan.py --sample

Exit codes: 0 ok, 2 bad input, 3 input file missing or unreadable.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

SAMPLE = Path(__file__).resolve().parent.parent / "assets" / "sample_plan_input.json"
SEASONS = ("Spring", "Summer", "Fall")
PACES = ("light", "balanced", "fast")
HEAVY_CREDITS = 16
FULL_TIME_CREDITS = 12
HARD = 4
MAX_TERMS = 16


def fail(message: str, code: int = 2):
    print(message, file=sys.stderr)
    sys.exit(code)


# Terms are represented as (season, year) pairs while scheduling. The text label is only for display.

def parse_term(text) -> tuple[str, int]:
    try:
        season, year = str(text).split()
        season = season.capitalize()
        if season not in SEASONS:
            raise ValueError
        return season, int(year)
    except ValueError:
        fail(f"Terms look like 'Fall 2026', 'Spring 2027' or 'Summer 2027' (got {text!r}).")


def next_term(season: str, year: int) -> tuple[str, int]:
    return {"Fall": ("Spring", year + 1), "Spring": ("Summer", year), "Summer": ("Fall", year)}[season]


def term_range(start, end) -> list[tuple[str, int]]:
    terms, current = [], start
    while True:
        terms.append(current)
        if current == end:
            return terms
        if len(terms) >= MAX_TERMS:
            fail("graduation_term must be after start_term and within about five years.")
        current = next_term(*current)


def label(term: tuple[str, int]) -> str:
    return f"{term[0]} {term[1]}"


# Input data stays deliberately close to the JSON format, with a little normalization for scheduling.

def prereq_met(prereqs: list, done: set[str]) -> bool:
    """Each entry is a course code (needed) or a list of codes (any one of them is enough)."""
    return all((p in done) if isinstance(p, str) else any(x in done for x in p) for p in prereqs)


def prereq_codes(prereqs: list) -> list[str]:
    return [x for p in prereqs for x in ([p] if isinstance(p, str) else p)]


def load_courses(data: dict) -> list[dict]:
    courses, seen = [], set()
    for raw in data.get("courses") or []:
        code = str(raw.get("code", "")).strip()
        credits = raw.get("credits")
        if not code or not isinstance(credits, (int, float)) or credits <= 0:
            fail(f"Every course needs a code and positive credits (problem near {raw!r}).")
        if code in seen:
            fail(f"Course {code} is listed twice.")
        seen.add(code)
        difficulty = raw.get("difficulty")
        if difficulty is not None and not (isinstance(difficulty, int) and 1 <= difficulty <= 5):
            fail(f"difficulty for {code} must be a whole number from 1 to 5, or left out.")
        offered = [str(s).capitalize() for s in raw.get("offered") or []]
        if any(s not in SEASONS for s in offered):
            fail(f"offered for {code} may only contain Fall, Spring and Summer.")
        courses.append({
            "code": code, "title": raw.get("title") or code, "credits": credits,
            "prereqs": raw.get("prereqs") or [], "offered": offered,
            "core": bool(raw.get("core")), "difficulty": difficulty, "summer_ok": raw.get("summer_ok"),
        })
    return courses


def add_placeholders(courses: list[dict], data: dict, goals: dict) -> None:
    """Represent undecided elective/minor credits as slots the schedule can make room for."""
    for key, title, core in (("extra_credits_needed", "Open elective", False), ("minor_credits", "Minor course (to be chosen)", False)):
        amount = float(goals.get(key) or 0)
        for n in range(math.ceil(amount / 3)):
            credits = min(3, amount - 3 * n)
            courses.append({"code": f"{title} {n + 1}", "title": title, "credits": credits, "prereqs": [], "offered": [],
                            "core": core, "difficulty": None, "summer_ok": True, "placeholder": key})


def descendants(courses: list[dict]) -> dict[str, int]:
    """How many courses depend, directly or not, on each course. Also rejects prerequisite loops."""
    codes = {c["code"] for c in courses}
    children = {c: set() for c in codes}
    for course in courses:
        for p in prereq_codes(course["prereqs"]):
            if p in codes:
                children[p].add(course["code"])
    memo: dict[str, set[str]] = {}
    visiting: set[str] = set()

    def walk(code: str) -> set[str]:
        if code in memo:
            return memo[code]
        if code in visiting:
            fail(f"Prerequisites for {code} loop back on themselves. Check the prerequisite lists.")
        visiting.add(code)
        found: set[str] = set()
        for child in children[code]:
            found |= {child} | walk(child)
        visiting.discard(code)
        memo[code] = found
        return found

    return {code: len(walk(code)) for code in codes}


# ---- Scheduling ------------------------------------------------------------------------------

def schedule(courses, terms, caps, target, done_start, depth, internship_goal):
    remaining = {c["code"]: c for c in courses}
    done, plan = set(done_start), []

    def priority(c):
        # Schedule named courses before placeholder credits. A real course may unlock several others, so
        # courses with more downstream dependents go first; internship plans also favor core courses.
        slot_rank = 1 if c.get("placeholder") else 0
        core_rank = 0 if c["core"] else 1
        if internship_goal:
            return (slot_rank, core_rank, -depth[c["code"]], c["code"])
        return (slot_rank, -depth[c["code"]], core_rank, c["code"])

    for term in terms:
        season = term[0]
        cap = caps[term]
        # For regular terms, target is the preferred load. Summer is governed by its own cap instead.
        goal = cap if season == "Summer" else min(target, cap)
        chosen, used = [], 0.0
        candidates = []
        for c in remaining.values():
            if not prereq_met(c["prereqs"], done):
                continue
            if c["offered"] and season not in c["offered"]:
                continue
            if season == "Summer":
                # A student can explicitly allow or rule out a summer course. Without an override,
                # missing difficulty falls back to 3, while scores of 4 or 5 keep the course out.
                easy = c["summer_ok"] is True or (c["summer_ok"] is None and (c["difficulty"] or 3) < HARD)
                if not easy:
                    continue
            candidates.append(c)
        for c in sorted(candidates, key=priority):
            if used + c["credits"] <= goal:
                chosen.append(c)
                used += c["credits"]
        for c in chosen:
            del remaining[c["code"]]
        done |= {c["code"] for c in chosen}
        plan.append({"term": term, "cap": cap, "credits": used, "courses": chosen})
    return plan, list(remaining.values())


def explain_unscheduled(course, terms, caps, scheduled_codes, completed) -> str:
    usable = [t for t in terms if caps[t] > 0 and (not course["offered"] or t[0] in course["offered"])]
    if not usable:
        return "not offered in any term you have left (per the offered list)"
    waiting = [p for p in prereq_codes(course["prereqs"]) if p not in scheduled_codes and p not in completed]
    if waiting:
        return f"waiting on prerequisite {', '.join(waiting)}"
    return "no room before the graduation term at your credit limits"


def build(data: dict) -> dict:
    goals = data.get("goals") or {}
    start, end = parse_term(goals.get("start_term")), parse_term(goals.get("graduation_term"))
    terms = term_range(start, end)
    pace = str(goals.get("pace") or "balanced").lower()
    if pace not in PACES:
        fail(f"pace must be one of {', '.join(PACES)}.")
    max_credits = float(goals.get("max_credits_per_term") or 15)
    summer_cap = float(goals.get("summer_credit_cap") if goals.get("summer_credit_cap") is not None else 6)
    allow_summer = bool(goals.get("allow_summer"))
    internship_cap = float(goals.get("internship_term_cap") or 0)
    internship = parse_term(goals["internship_term"]) if goals.get("internship_term") else None

    caps = {}
    for term in terms:
        if term == internship:
            caps[term] = internship_cap
        elif term[0] == "Summer":
            caps[term] = summer_cap if allow_summer else 0.0
        else:
            caps[term] = max_credits

    courses = load_courses(data)
    add_placeholders(courses, data, goals)
    if not courses:
        fail("No remaining courses were given.")
    completed = {str(c).strip() for c in data.get("completed") or []} | {str(c).strip() for c in data.get("in_progress") or []}
    known = {c["code"] for c in courses} | completed
    warnings = []
    for course in courses:
        for p in prereq_codes(course["prereqs"]):
            if p not in known:
                warnings.append(f"{course['code']} lists prerequisite {p}, which is neither finished nor on the remaining list. Treated as missing; check it.")
    depth = descendants(courses)

    regular = [t for t in terms if t[0] != "Summer" and caps[t] > 0]
    needed = sum(c["credits"] for c in courses)
    average = needed / max(len(regular), 1)
    targets = {"light": math.ceil(average), "balanced": max(math.ceil(average), FULL_TIME_CREDITS), "fast": max_credits}
    target = max(1, min(max_credits, targets[pace]))

    notes = []
    used_target = target
    # Try the requested pace first. If it cannot fit everything, raise the regular-term target a credit
    # at a time; this finds the lightest load that still meets the student's target graduation term.
    plan, left = schedule(courses, terms, caps, used_target, completed, depth, internship is not None)
    while left and used_target < max_credits:
        # Raise the load one credit at a time, so the plan stays as light as the graduation date allows.
        used_target = min(used_target + 1, max_credits)
        plan, left = schedule(courses, terms, caps, used_target, completed, depth, internship is not None)
    if used_target > target and not left:
        notes.append(f"To finish by {label(end)}, the load had to rise from about {target:g} to {used_target:g} credits a term.")

    scheduled_codes = {c["code"] for t in plan for c in t["courses"]}
    unscheduled = [{"code": c["code"], "title": c["title"], "reason": explain_unscheduled(c, terms, caps, scheduled_codes, completed)} for c in left]

    flags = []
    term_index = {t["term"]: i for i, t in enumerate(plan)}
    for entry in plan:
        name, courses_here = label(entry["term"]), entry["courses"]
        hard = [c["code"] for c in courses_here if (c["difficulty"] or 0) >= HARD]
        if entry["credits"] > HEAVY_CREDITS:
            flags.append(f"{name}: heavy load, {entry['credits']:g} credits.")
        if len(hard) >= 2:
            flags.append(f"{name}: {len(hard)} hard classes at once ({', '.join(hard)}). Consider moving one.")
        if entry["term"][0] == "Summer" and courses_here:
            flags.append(f"{name}: summer sessions are usually shorter, so each week covers more and there is less room to recover from a bad week.")
            if hard:
                flags.append(f"{name}: {', '.join(hard)} is marked hard and is in a summer term. Think twice.")
        if entry["term"][0] != "Summer" and 0 < entry["credits"] < FULL_TIME_CREDITS and entry["term"] != internship:
            flags.append(f"{name}: under {FULL_TIME_CREDITS} credits. Check full-time rules for aid, housing and visas with your school.")
        if entry["term"] == internship and courses_here:
            flags.append(f"{name}: classes planned during your internship term ({entry['credits']:g} credits).")
    if internship in term_index:
        late = [c["code"] for t in plan[term_index[internship] + 1:] for c in t["courses"] if c["core"]]
        if late:
            flags.append(f"Core classes after your internship term: {', '.join(late)}. Employers may expect them first.")

    # This is a rough capacity estimate, not a promise that extra courses meet a minor's requirements.
    capacity = sum(caps.values())
    return {
        "terms": [{"term": label(t["term"]), "credits": t["credits"], "cap": t["cap"],
                   "courses": [{"code": c["code"], "title": c["title"], "credits": c["credits"],
                                "placeholder": bool(c.get("placeholder"))} for c in t["courses"]]} for t in plan],
        "unscheduled": unscheduled, "flags": flags, "warnings": warnings, "notes": notes,
        "summary": {"credits_remaining": needed, "pace": pace, "target_per_term": target,
                    "room_left_at_max_load": max(capacity - needed, 0), "graduation_term": label(end)},
    }


def render(result: dict) -> str:
    lines = []
    for t in result["terms"]:
        header = f"{t['term']} - {t['credits']:g} credits"
        if not t["courses"]:
            lines.append(f"{header} (no classes planned)")
            continue
        lines.append(header)
        lines += [f"  {c['title']} ({c['credits']:g})" if c["placeholder"] else f"  {c['code']}: {c['title']} ({c['credits']:g})"
                  for c in t["courses"]]
    if result["unscheduled"]:
        lines.append("Could not place:")
        lines += [f"  {u['code']}: {u['reason']}" for u in result["unscheduled"]]
    for title, key in (("Flags", "flags"), ("Check", "warnings"), ("Notes", "notes")):
        if result[key]:
            lines.append(f"{title}:")
            lines += [f"  - {item}" for item in result[key]]
    s = result["summary"]
    lines.append(f"Summary: {s['credits_remaining']:g} credits left by {s['graduation_term']}, pace {s['pace']}, "
                 f"about {s['target_per_term']:g} per term, room for roughly {s['room_left_at_max_load']:g} more credits at your max load.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", help="JSON file with goals, completed courses and remaining courses")
    parser.add_argument("--json", action="store_true", help="print the plan as JSON instead of text")
    parser.add_argument("--sample", action="store_true", help="offline demo with made-up courses in assets/sample_plan_input.json")
    args = parser.parse_args(argv)
    path = SAMPLE if args.sample else Path(args.input) if args.input else None
    if path is None:
        fail("Give --input FILE (or --sample).")
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        fail(f"Could not read the plan input {path}: {type(exc).__name__}.", 3)
    if not isinstance(data, dict):
        fail("The plan input must be a JSON object with goals and courses.")
    result = build(data)
    print(json.dumps(result, indent=1) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
