# RF-One UI Rules

**Status:** standing rules, approved by the Product Owner (UI_NAVIGATION_AND_LOCAL_TIME_001, 2026-09-27).
**Applies to:** every screen of every RF-One app a person uses (RF-One Web, Tips, and any future app on the RF-One login), and every future UI refinement.
**Authority:** these rules govern how things are *shown*. They never change what is stored, computed or decided.

---

## 1. Times are local to the Location, never UTC

Every time shown to a person is in the local time of the Location the fact belongs to. The zone comes from that Location's own `Location.timezone` (IANA), e.g. Winter Park → `America/New_York`.

- UTC remains the storage and computation format. Only the display changes.
- State the zone once per page or card (e.g. "Times are Rome's Flavours - WP local time (America/New_York)"). Where a single time stands alone, e.g. a "Last update", append the abbreviation (`EDT`/`EST`). Do not repeat it on every table row.
- If a Location has no timezone configured, show the UTC instant and label it "UTC". Never guess a zone.
- Implementation: `rfone_data_store/display_format.py` (`local_datetime`, `zone_label`). Both apps register it as the `|local_dt(tz)` template filter. No app keeps its own copy.

## 2. Employees are shown as "Surname I."

In operational displays and reports for people, an employee is shown as surname plus first-name initial: "Tatiana Ceban" → **Ceban T.**; "Andrew Muller" → **Muller A.**

- Never show a technical identifier (a Clover employee id, an internal `Employee #id`) where a person reads the page. The one exception is the last-resort fallback when no name exists at all.
- The full name is kept where it is genuinely needed. Example: matching a payee to a bank recipient in Tips Payment Control.
- This is a display rule only. Names and identifiers stay in the database unchanged.
- Implementation: `display_format.employee_short_name`, template filter `|short_name`. The surname is everything after the first word ("Maria De Luca" → "De Luca M."). A single word is shown as it is.

## 3. Frequent actions live where they are needed

A frequent action is available on the page where the need arises. The person does not have to open a sub-page just to perform it. Example: Sync Now on the Tips "Clover Acquisition" tab.

- The action on that page calls the **one central implementation**, with the same authorization, CSRF and duplicate protection. It is never a second copy. Example: the Tips Sync Now form posts to RF-One Web's `/clover-acquisition/sync-now`.
- The full page stays reachable, as an optional link, for history, details, errors and rarer actions.
- Keep such an inline block short and operational: state, the action, the link. No technical explanations.

## 4. Every sub-page shows its path, not a generic "Home" link

Every sub-page shows the hierarchical path that leads to it, and every level of that path is clickable:

```
RF-One > Tips > Distribution Rules > Rule #12
RF-One > Tips > Saved Periods > Period #7
RF-One > Accounts > Edit account
RF-One > Clover Acquisition
RF-One > Tips > Clover Acquisition        (when opened from the Tips tab)
```

- The path reflects the **real** structure of the interface and the Domains. Do not invent a level to build a breadcrumb.
- A heading on the Home page that is not itself a page (e.g. "Settings", "Administration") is not a level.
- A general RF-One capability is not presented as a child of a Domain just because that Domain links to it. The Domain level appears only when the person actually came from there (Clover Acquisition: `?from=tips`).
- The last level is the current page and is not a link. A level whose address is not configured is shown unlinked.
- Implementation: the `breadcrumb(items)` macro in `templates/_nav_macros.html`, identical in RF-One Web and Tips, plus the `.breadcrumb` style in each app's `rf-one.css`. The Tips `base.html` builds RF-One > Tips > *tab* automatically. A detail page adds its levels by setting `crumbs`.

---

## Local days (companion rule, UI_OFFICIAL_ENTRY_AND_LOCAL_DAYS_001)

A date a person picks, for a Clover Historical Backfill or for the Tips Clover Acquisition data filter, is the Location's **local civil day**: 00:00:00 → 23:59:59 in the Location's timezone. RF-One converts it to UTC internally. The zone's own rules handle EDT/EST changes.

This is not the Tips Business Date, which is the configured operating day (currently 04:00 → 04:00). The operating-day cutoff is never used for these dates.

Implementation: `rfone_data_store/local_calendar.py`.

---

## Where these rules are applied today

| Rule | RF-One Web | Tips | Training (hosted in RF-One Web) |
|---|---|---|---|
| 1 Local time | Clover Acquisition; Tips saved-period validation; Bank (instrument audit, monthly sources); Organization attention history | Clover Acquisition tab; Calculate Tips drill-down; Host Audit screen and CSV export; Saved Periods and report; rule versions | quiz and attempt times |
| 2 Surname I. | Clover Acquisition; saved-period validation; Bank cardholder list and "changed by"; trainer student list | every operational table; Host Audit CSV | trainer student list and breadcrumb |
| 3 Inline action | — | Sync Now on the Clover Acquisition tab | — |
| 4 Breadcrumb | every sub-page | every page | every page |

**Deliberately kept, with a reason:**

- Full names stay on account administration, Profile, and Organization configuration: they manage identities, not operational reading.
- Full names stay on Tips Payment Control, to match payees.
- Full names stay on the Bank card edit page, to assign the right cardholder.
- A student's own full name stays on the trainer's student page heading.
- Compensation is outside the scope of UI_OFFICIAL_ENTRY_AND_LOCAL_DAYS_001 (Product Owner instruction) and is not yet aligned.

**Needs a Product Owner decision before it can be aligned:**

- Validity starts (`valid_from`) of Organization positions and Bank cardholders are printed as stored, with a `+00:00` offset. Whether each is a calendar date or an instant decides how it should be shown. Converting midnight UTC to local time would show "20:00 the day before".
