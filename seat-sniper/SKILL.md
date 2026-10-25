---
name: seat-sniper
description: Checks full classes on a schedule and alerts the student when a seat appears, then plans their degree semester by semester around their goals. Use when a class is full or waitlisted, the student wants to know when a seat opens, is picking classes for next term or asks which classes to take, whether they can graduate on time, whether summer classes are a good idea, or wants a lighter load, an internship term or a minor. Built for Arizona State University students (ASU class search and the DARS report).
---

# Seat Sniper

Seat Sniper helps with two stressful parts of college planning. It can keep an eye on a full class and let the
student know when a seat appears, or turn their degree requirements and goals into a semester-by-semester draft.
Those jobs can work together: if a class in the plan is full, offer to watch it. The student still does the
registering, and the plan still gets checked with an advisor.

The scripts need Python 3 and no extra packages. For seat checks, Cubbie reads the school's class-search page
and passes the seat count to the script; the script itself does not browse the web.

## When to use

- "CSE 355 is full, tell me when a seat opens"
- "I'm on the waitlist for ENG 102, can you watch it?"
- "Plan out my classes until I graduate" / "which classes should I take next semester?"
- "I want an internship after sophomore year, what should I take first?"
- "I came in with a lot of credits, can I go light or add a minor?"
- "Should I take this in the summer?"

Seat checks happen on a schedule, so do not promise that the alert will arrive at the exact instant a seat opens.
Do not use Seat Sniper to register, enroll or drop classes, or to replace an advisor's sign-off.

## Ground rules

- **Alerts are not enrollment.** The student opens the class-search link and registers for themselves. A watch
   only records what the page showed; it never changes their account.
- **Ask before setting anything in motion.** Get the student's yes before creating a repeating check-in, and
   confirm whether they want a phone call if they do not reply to an alert.
- **Stick to evidence.** Read seat counts from the class-search page, requirements from the student's DARS and
   the ASU catalog, and difficulty from the student. If a prerequisite, offering or seat count is unclear, say so
   and ask. Guessing can cost the student time and tuition.
- **Treat every plan as a draft.** Ask the student to check it against the current catalog and with an advisor
   before registering.
- **Handle DARS carefully.** It includes personal details that do not belong in a course plan. Use the course
   information only; never repeat or save the student's ID number.

## Seat watch

1. Ask for the course code and term. Ask for a section or class number only if the student wants one specific
   section; otherwise, any section of that course is fine. Keep questions one at a time and offer a sensible
   default when there is one.
2. Before saving anything, summarize the schedule and ask for a yes. For example: "I'll check every 15 minutes
   and text you if a seat shows up. If you haven't replied after 5 minutes, I can call. Would you like calls, or
   texts only?" Use `--no-call` for text-only. Use the interval the student chose, and be clear that checks are
   periodic, not continuous.
3. Save the watch and note the id it prints:

   ```bash
   python3 scripts/watch.py add --course "<code>" --section "<number>" --term "<term>" --url "<class search link>" [--no-call]
   ```

4. Only after the yes, create a repeating check-in at the chosen interval. Write it so it is still clear when it
   runs days later:
   "Seat Sniper check for <course> (watch id <id>): follow the Seat Sniper check steps, then stop quietly if nothing changed."
5. Each check-in does this:
   1. Open the class-search page in Cubbie's browser and read the open-seat count (and waitlist, if shown).
      ASU's page is a JavaScript app, so a plain page read will not show the results. The current browser notes
      are in `references/schools.md`.
   2. Record what you saw. Pass the student's local time so the gaps between checks are right:

      ```bash
      python3 scripts/watch.py check --id <id> --open-seats <n> [--waitlist <w>] --now "<student local time, ISO 8601>"
      ```

      If the page could not be read, run the same command with `--unreadable` instead of `--open-seats`.
   3. Use the first word of the output to decide what happens next:
      - `ALERT` or `STILL_OPEN`: text the student (below). If calls are on, create a one-time check-in for 5
        minutes later: "Seat Sniper follow-up for <course> (watch id <id>): run the followup step."
      - `NO_CHANGE`, `CLOSED_AGAIN`, `UNREADABLE`: send nothing. A seat that filled back up is not worth a text.
      - `TELL_STUDENT`: text once that the class page could not be read, and offer to retry or stop.
6. The one-time follow-up runs:

   ```bash
   python3 scripts/watch.py followup --id <id> --now "<student local time, ISO 8601>"
   ```

   `CALL`: phone the student once with a short message. `SKIP`: do nothing.
7. When the student replies, record it with `python3 scripts/watch.py ack --id <id> --now "<time>"`. Then ask
   whether they got the seat. If they did, or they want to stop watching, remove the watch with
   `python3 scripts/watch.py remove --id <id>` and cancel its repeating check-in. Use
   `python3 scripts/watch.py list` to see the active watches.

Alert text:

```text
Seat open: CSE 355 (section 12345), 2 seats.

Register now:
<class search link>

Reply "got it" when you've grabbed one, or "stop" to stop watching.
```

Call message: "Hi, it's Cubbie. A seat just opened in <course>. Check your texts for the link."

## Degree plan

Planning uses `scripts/plan.py`. It can only plan from the courses and details in its input file; it does not
look up the catalog or interpret a DARS report on its own. The input format and DARS workflow are in
`references/planner.md`.

1. **Start with the student's goals.** Ask one question at a time and offer a default they can accept with
   "yes":
   graduation term, whether and when they want an internship (which term they will be away), credits already
   earned or coming in with, interest in a minor, the most credits per term they can handle, and which remaining
   classes they expect to be hardest. Save the answers to memory so re-plans do not start over.
2. **Summer defaults to off.** Plan no summer classes unless the student asks. If they do, tell them summer
   sessions are usually shorter, so each week covers more and a bad week is harder to recover from, and keep
   summer light and away from the classes they called hard.
3. **Ask for the DARS report.** The student can send a PDF or screenshots; never ask them to sign in through you.
   Separate completed, in-progress and remaining courses. If a requirement says "choose N from this list," ask
   what they want to take or leave those credits open for now. The DARS may not include prerequisites or which
   terms a course runs, so check the ASU catalog and tell the student what you found. If a detail is still
   uncertain, leave it out of the input and call it unverified in your reply.
4. **Build the plan.** Write the input file and run:

   ```bash
   python3 scripts/plan.py --input plan_input.json
   ```

   Add `--json` for structured output. `python3 scripts/plan.py --sample` shows the idea with made-up courses.
5. **Share the useful part first.** The full plan can be long, so put it in a PDF and text a short summary: how
   many terms it takes, the heaviest term and the one or two most important flags. Remind the student to confirm
   the draft with an advisor before registering.
6. **Revise it when life changes.** If a goal changes, a class is failed or dropped, new credits arrive, or a
   term passes, update the input file and run the planner again. In two or three lines, say what moved and why.
   You can offer one reminder before each registration window, but create it only after the student agrees.
7. **Close the loop.** When a class the plan needs is full at registration, offer to watch it with the seat watch.

## Replies

Keep texts short and plain: one idea per message, no tables or Markdown decoration. Put each link on its own
line and lead with the answer. Send long plans and course lists as a PDF, with a one-line summary in the text.

Plan headline example:

```text
Plan is ready: 5 terms, lightest load 12 credits, no summer.
2 flags: CS 310 can only land after your internship term, and Spring 2028 is under 12 credits.
Full plan attached. Check it with your advisor before you register.
```

## When something fails

| Situation | What to do |
| --- | --- |
| Class page will not load or has no seat count | Run the check with `--unreadable`; the script tells you when to text the student |
| The page asks for a sign-in or blocks Cubbie | Say so once, and ask the student to send a screenshot of the seat count if they want a one-off check |
| Class not found | Ask for the course code and term again, or the class number |
| DARS unreadable or incomplete | Say what is missing and ask for a clearer file; do not guess requirements |
| `plan.py` exits 2 | Read the message, fix the input file, rerun |
| `plan.py` lists courses it could not place | Tell the student which and why, and suggest a later graduation term, a summer term or a heavier load, and let them choose |
| The student wants Cubbie to register for them | Decline: the student registers themselves; offer the alert instead |
