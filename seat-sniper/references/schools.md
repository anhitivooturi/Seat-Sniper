# Checking seats at a school

Seat Sniper does not fetch class-search pages itself. Cubbie opens the school's search page, reads what it can,
and passes the seat count to the watch script. Keep the notes here honest about what has actually been tested;
class-search sites change, and a guess about a seat count is worse than saying the page could not be read.

## Arizona State University

- Class search: https://catalog.apps.asu.edu/catalog/classes
- The results are rendered by JavaScript. A plain page read only shows the message asking for JavaScript, so use
  Cubbie's browser to see the actual search results.
- No sign-in is needed to search classes.
- Still to verify during a real run: the exact search fields, the labels used for seat counts, and whether a
  direct link to one class is available. Add the observed details here after checking the live page.

### Reading one class

1. Open the class-search page in Cubbie's browser.
2. Choose the term the student gave you.
3. Search by course code, or by class number when the student provided one.
4. Find the requested section. If they did not name a section, check every section listed for that course.
5. Read the open-seat count and, when available, the waitlist count. For an unspecified section, report the
  largest open-seat count; for a requested section, use that section's count.
6. If the page does not show a count you can trust, mark the check unreadable. Do not estimate.

### Notes for the next live test

- How seats appear on a results row (for example "open" and "total" values):
- Whether the class number search works, and the field it uses:
- Anything that blocks automated browsing, such as a captcha or rate limit:
- A faster way to open one class directly:

## Adding another school

When adding a school, record its class-search link, whether a sign-in is required and exactly how the page labels
seat counts. Mention supported schools in the reply so the student knows what to expect before starting a watch.
