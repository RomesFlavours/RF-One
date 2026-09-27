# UI_NAVIGATION_AND_LOCAL_TIME_001 — Clover Acquisition refinement and RF-One UI Rules

**Status:** deployed on AWS on 2026-09-27. Anonymous checks were run on the published interface. The signed-in checks (Sync Now from Tips, return to the Tips tab, shared session) are still to be done by the Product Owner, because they need a real RF-One login.
**Commits:** `0529c55` (code, tests, rules), then the follow-up commit that adds this report and the Infrastructure README update.

## 1. Product Owner decisions

| Date | Decision |
|---|---|
| 2026-09-27 | Option A of `03 Software/Infrastructure/README.md`: one CloudFront entry in front of `rfone-web` (`/`) and `rfone-tips` (`/tips/`), so Tips shares the RF-One session and can offer Sync Now. |
| 2026-09-27 | Authorization for the IAM policy that lets `rfone-tips` read the shared session secret `rfone-web/flask-secret-key`. |

## 2. What changed

| Area | Change |
|---|---|
| Local time | `rfone_data_store/display_format.py`: every time is shown in the Location's `timezone` (Winter Park → America/New_York, EDT/EST). The zone is stated once per page. UTC is used only when a Location has no timezone, and is then labelled "UTC". Nothing stored changes. |
| Names | "Surname I." (`Ceban T.`) replaces Clover employee ids and internal `Employee #id`. It applies to the Clover Acquisition "requested by" and "signed in as", the Tips imported data, Calculate Tips, the order drill-down, Host Audit, and Saved Periods and their reports. Payment Control keeps full names, because they are needed to match payees. |
| Tips tab | Shows the last update (local time), Sync Now, "Sync in progress" with the button disabled while a job runs, and an optional "Open Clover Acquisition" link. Sync Now is a form posting to RF-One Web's `/clover-acquisition/sync-now`. That means the same login, `CLOVER_ACQUISITION` access, CSRF token and one-job lock as the full page. `return_to=tips` only brings the person back to the tab. Tips has no Sync Now route of its own. |
| Full page | Local times, no "(UTC)", "Surname I.". Breadcrumb: "RF-One > Clover Acquisition", or "RF-One > Tips > Clover Acquisition" when opened from Tips (`?from=tips`). |
| Breadcrumb | Macro `_nav_macros.html`, identical in both apps. It is used on all RF-One Web sub-pages (Accounts, Legal Entities, Organization and its pages, Compensation, Bank, Profile, Tips saved periods, Training trainer pages, work in progress) and on all Tips pages. Home headings such as "Settings" are not levels. |
| Single host | CloudFront `E3MIBLH55LEYD8`. Tips accepts the `/tips` prefix. Its session cookie keeps RF-One Web's attributes. The Tips Domain card points to `/tips/`. |
| Rules | `03 Software/Shared UI/UI Rules.md` and the "RF-One UI Rules" section in `CLAUDE.md`. |

Not changed: the acquisition engine, the Sync Now window, Historical Backfill dates, Live Sync (still not active), data, permissions and the database schema (no migration).

## 3. Tests (local)

All 34 suites pass: 25 for RF-One Web, 5 for Tips, and 4 for the Data Store (Clover jobs, acquisition, Live Sync, Tips finalized period).

New tests:
- `RF-One Web/tests/test_ui_navigation_and_local_time_http.py` (32 checks)
- `Tips/test_clover_acquisition_tab_http.py` (28 checks)

Adapted tests (breadcrumb instead of the "RF-One Home" link, "Surname I." instead of the full name, `?from=tips`):
- `test_bank_instrument_assignment_http.py`
- `test_bank_reconciliation_http.py`
- `test_clover_acquisition_http.py`
- `test_clover_acquisition_moved_http.py`
- `test_tips_saved_periods_navigation_http.py`

## 4. Production (anonymous checks on `https://dn1l56t5jz22u.cloudfront.net`)

| Check | Result |
|---|---|
| `/`, `/clover-acquisition`, `/tips/runs` | 302 to the RF-One login, with `next` |
| Every Tips tab under `/tips/…` | 200 |
| Tips tab | "Last update: 2026-09-27 09:02 EDT", a sign-in link back to `/tips/`, and "Open Clover Acquisition?from=tips" |
| "UTC" on Tips pages | none |
| Employees in the imported data | "Ceban T.", "Martini A.", …; ids only in the Order/Payment id columns |
| Breadcrumb | e.g. RF-One > Tips > Distribution Rules > Roles > New Role, every upper level a link |

AWS references:
- RDS snapshot `rfone-dev-pre-ui-navigation-20260927t142921z`
- S3 backups `backups/*-pre-ui-navigation-20260927t142921z.zip`
- CodeBuild `rfone-web-build:e59d9f9c…` and `rfone-tips-build:44e57252…`
- `rfone-tips` image `sha256:c685cf71…`
- IAM inline policy `rfone-tips-shared-session-secret-read`

## 5. Open points

1. **Signed-in checks for the Product Owner**, on `https://dn1l56t5jz22u.cloudfront.net`:
   - sign in, open Tips, and check that Sync Now appears;
   - press Sync Now; you should come back to the tab with "Sync in progress";
   - open Clover Acquisition from Tips and check the breadcrumb and local times;
   - use each breadcrumb level to go back.
2. The RF-One entry address is now the CloudFront one. Bookmarks to `vhmsm9mgh8…` still work for RF-One Web, but the Tips link does not work from there. Redirecting the old hostnames, or adding a definitive RF-One domain, is a separate decision.
3. Historical Backfill interprets its dates as UTC days. This was not changed, as requested. In local time, the window therefore appears to run from 20:00 to 19:59 EDT. Whether to switch it to local days is a Product Owner decision.
4. The Tips "Imported Clover data" filter also uses UTC days. The times shown are local, so an order at 22:00 EDT falls under the next UTC day.
5. Not yet aligned with the rules: Bank timestamps, Training's own pages, and full names in the Host Audit CSV.
6. `rfone-tips/flask-secret-key` is no longer used. It can be deleted.
