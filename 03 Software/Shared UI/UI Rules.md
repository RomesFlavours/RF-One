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
RF-One > Tips > Configuration > Rule #12
RF-One > Tips > Saved Periods > Period #7
RF-One > Accounts > Edit account
RF-One > Clover Acquisition
RF-One > Tips > Clover Acquisition        (when opened from the Tips tab)
```

- The path reflects the **real** structure of the interface and the Domains. Do not invent a level to build a breadcrumb.
- A heading on the Home page that is not itself a page (e.g. "Settings", "Administration") is not a level.
- A general RF-One capability is not presented as a child of a Domain just because that Domain links to it. The Domain level appears only when the person actually came from there (Clover Acquisition: `?from=tips`).
- The last level is the current page and is not a link. A level whose address is not configured is shown unlinked.
- Implementation: the `breadcrumb(items)` macro in `templates/_nav_macros.html`, identical in RF-One Web and Tips, plus the `.breadcrumb` style in each app's `rf-one.css` (identical rules, `›` separator). The Tips `base.html` builds RF-One > Tips > *tab* automatically. A detail page adds its levels by setting `crumbs`.
- Tips follows the Compensation layout (TIPS_NAVIGATION_STANDARD_001): the header names RF-One only (never "RF-One · Tips") and links to RF-One Home; the breadcrumb comes first; the Tips menu follows, in this order — Clover Acquisition, Calculate Tips, Saved Periods, Payment Control, Configuration (always last). A contextual page is not a menu entry: Explain / Audit Host Tips is opened from Calculate Tips and reads RF-One > Tips > Calculate Tips > Explain / Audit Host Tips.

## 5. After a row action, the person is back on that row

Product Owner standard UI_ROW_RETURN_001 (2026-10-10). When an action is started from a button (or a select) on a list row — Edit, Rule, Disable, Confirm… — the person ends on **the same record, at the same place on the screen**, never at the top of the list.

- **Before** the modal opens or the action runs, the page keeps: the record's stable identity (never its index), its position on screen and in its own scroll container, and the list's search, filters, sort and page.
- **After** Save, Confirm, Cancel, Esc or closing the modal: the list context is kept, the view returns to that record with the same visual position, and focus goes back to the button that was used, if it is still shown. This holds when the save reloads the page too.
- A record that **moves** in the sort is shown in its new place; the sort stays correct.
- A record that **disappears** (deleted, merged, no longer matching the filters): the next remaining row takes its place, else the previous one; an empty list shows its empty state with filters and search unchanged. Filters are never changed to bring a record back.
- A **refusal** inside a modal keeps the modal open, with the values and the reason. The return happens when the modal is closed.
- **Multiple selections** follow their own existing rules; nothing new is selected and no hidden selection is kept against those rules.
- The return belongs to **that action only**. A normal opening of a page (a link, a search, another tab or session) never restores an old position.
- The busy cursor and spinner (`rf-one-busy.js`) are unchanged.

Implementation: `static/js/rf-one-row-return.js` (RF-One Web), one implementation for every list.
- A page opts in by marking each row with a stable `data-rr-key`, for example `<tr data-rr-key="who:39">`. A client-side search box whose value must survive a reload carries `data-rr-state` and an `id`. Server-side search, filters, sort and page stay in the URL, which the page's own redirect keeps.
- The record travels in `sessionStorage` (this tab only). It is used once, by the next load of the same page within a minute of leaving it.
- The Bank menu macro (`_bank_macros.html` → `module_nav`) loads the script on every Bank page.

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
| 5 Row return | Bank: Configuration (WHAT, WHY, WHO, Entity); Source (Sources, source profiles); Review Transactions (To Reconcile, Reconciled) | — (not yet aligned) | — (not yet aligned) |

Rule 5 is defined for every module. Lists outside Bank (Tips, Training, Compensation, Organization, Selection…) adopt it when they are next worked on, by loading `rf-one-row-return.js` and marking their rows. Within Bank, the Import and Review lists (batches, import files) and Monthly Export are not marked yet.

**Deliberately kept, with a reason:**

- Full names stay on account administration, Profile, and Organization configuration: they manage identities, not operational reading.
- Full names stay on Tips Payment Control, to match payees.
- Full names stay on the Bank card edit page, to assign the right cardholder.
- A student's own full name stays on the trainer's student page heading.
- **Compensation Period Summary** shows **first name + surname initial** ("Tatiana C."), by explicit Product Owner instruction for that screen only (COMPENSATION_PERIOD_SUMMARY_001, 2026-09-28): it is compared line by line with manual figures kept that way. Implementation: `display_format.employee_first_name_initial`, template filter `|first_name_initial`. Every other page keeps rule 2.
- Compensation is outside the scope of UI_OFFICIAL_ENTRY_AND_LOCAL_DAYS_001 (Product Owner instruction) and is not yet aligned.

**Needs a Product Owner decision before it can be aligned:**

- Validity starts (`valid_from`) of Organization positions and Bank cardholders are printed as stored, with a `+00:00` offset. Whether each is a calendar date or an instant decides how it should be shown. Converting midnight UTC to local time would show "20:00 the day before".
