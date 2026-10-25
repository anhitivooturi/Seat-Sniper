# Planning a degree

The planner takes a student's goals and remaining courses and lays them out term by term. It is deliberately
literal: it uses the details in the input file and does not check the catalog or DARS for you. That makes the
input step important. If an offering or prerequisite has not been verified, leave it out rather than filling in
a guess.

To see a made-up plan, run `python3 scripts/plan.py --sample`. The matching input file,
`assets/sample_plan_input.json`, is a useful starting point for the format below.

## Input file

```json
{
  "goals": {
    "start_term": "Fall 2026",
    "graduation_term": "Spring 2028",
    "pace": "light",
    "max_credits_per_term": 15,
    "allow_summer": false,
    "summer_credit_cap": 6,
    "internship_term": "Summer 2027",
    "internship_term_cap": 0,
    "extra_credits_needed": 6,
    "minor_credits": 9
  },
  "completed": ["CS 101", "MATH 101"],
  "in_progress": [],
  "courses": [
    {"code": "CS 201", "title": "Data Structures", "credits": 4, "prereqs": ["CS 101"],
     "core": true, "difficulty": 3, "offered": ["Fall", "Spring"]}
  ]
}
```

| Field | Meaning |
| --- | --- |
| `start_term`, `graduation_term` | The first term in the plan and the student's target finish term. Use a season and year, such as `Fall 2026`, `Spring 2027` or `Summer 2027`. |
| `pace` | `light` spreads the remaining credits across regular terms; `balanced` aims for at least 12 credits when the schedule allows; `fast` uses the normal-term maximum as its target. If the target graduation date requires a heavier load, the planner raises the target only as much as needed. |
| `max_credits_per_term` | The student's preferred upper limit for a regular term. Defaults to 15. The planner can still flag a term over 16 credits as heavy. |
| `allow_summer`, `summer_credit_cap` | Summer is excluded unless the student opts in. If enabled, the planner uses the summer cap (6 by default) and schedules courses marked `summer_ok: true`, or courses with difficulty below 4. A missing difficulty score is treated as 3; set `summer_ok: false` when a course should stay out of summer. |
| `internship_term`, `internship_term_cap` | The term the student expects to be away. Its cap defaults to 0. When an internship term is set, courses marked `core` get priority so prerequisites and important classes can land before it where possible. |
| `extra_credits_needed` | Credits the student still needs but has not chosen courses for yet. The planner represents them as open elective slots, using three-credit slots where possible. |
| `minor_credits` | Extra credits the student wants to take toward a minor. These appear as minor slots; whether the plan can fit them is visible in the output. |
| `completed`, `in_progress` | Course codes already completed or being taken. Both count as satisfied prerequisites from the first planned term. |
| `courses[].prereqs` | A string is a required course code. Every top-level entry is required; a nested list means any one code in that list is enough. Example: `["MAT 265", ["CSE 110", "CSE 120"]]`. |
| `courses[].offered` | Terms when the course is known to run: `Fall`, `Spring` or `Summer`. If this is unknown, omit the field and tell the student it has not been verified. |
| `courses[].core` | Set to `true` for a course that should come early, such as a major class needed before an internship. With an internship term in the plan, these courses receive priority. |
| `courses[].difficulty` | A 1-to-5 estimate supplied by the student. Omit it if they do not know. Scores of 4 and 5 are treated as hard when the planner checks a term. |
| `courses[].summer_ok` | Set to `true` or `false` to make an explicit exception to the summer rule for this course. |

## Reading a DARS report

A DARS report is the student's degree audit: it shows which requirements are complete, in progress or still open.
Use it as the source for the course list, then fill in details it may not contain:

- Put finished courses in `completed` and current ones in `in_progress`.
- Add each known remaining course to `courses`, including its credit count and title when available.
- For "choose N from a list", ask the student which classes they want, or leave the credits in
  `extra_credits_needed`.
- DARS often leaves out prerequisites and the terms a class is offered. Check the ASU catalog and tell the student
  where you found the details. If you cannot verify them, leave those fields out. Never guess.
- Skip the ID number and any other personal details. Only course codes, titles and credits matter.

## What the flags mean

| Flag | Why it is raised |
| --- | --- |
| Heavy load | The term is over 16 credits. That may be more than the student wants or can comfortably manage. |
| Hard classes together | At least two courses marked difficulty 4 or 5 landed in the same term. Consider moving one if the rest of the schedule allows. |
| Summer term | Any summer course triggers a note because summer sessions are shorter and move faster. A hard summer course gets an additional warning. |
| Under 12 credits | A regular term has fewer than 12 credits. This can affect full-time status, aid, housing or visas; the student should check their own school's rules. |
| Classes during internship | One or more courses landed in the term the student expected to be away. |
| Core after internship | A course marked `core` remains after the internship term. Prerequisites or the course schedule may have made an earlier placement impossible. |

The summary gives the credits remaining, selected pace, target load and the rough amount of capacity left before
graduation at the student's maximum load. That last number can help answer "could I fit a minor?" It is only a
capacity estimate, not confirmation that a particular minor's requirements will fit.

## When a course cannot be placed

The script gives the reason it could not place a course: it is not listed as offered in any remaining term, it is
waiting on a prerequisite, or there is no room before the target graduation date. Explain the tradeoff and let the
student choose whether to consider a later graduation date, summer classes, a higher credit limit or a different
course.
