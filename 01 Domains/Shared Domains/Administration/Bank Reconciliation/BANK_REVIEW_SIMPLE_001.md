# Compact transaction review and example selection

The manual WHO/WHY picker and immediate WHOM selector are preserved, including their routes, CSRF, identifiers and confirmation behavior. Each row on both queues now has a single Use as example button. Its read-only dialog identifies the movement and offers AI rule or counterparty photo, using the existing conversation links and preserving the return-to-row URL. Choosing an example never saves classifications, a rule or a photo.

Technical decision/review badges are removed from the unresolved table; duplicate labels and import-source names are readable. WHO/WHY selection is labeled explicitly, WHOM stays under the account. Review headings, filters and queue descriptions are shorter; the queue labels say Without WHO / With WHO, matching the existing split condition. Column filters retain Search but show Clear only when active. Existing accounting controls and transaction confirmation remain available. Automatic reconciliation statuses are displayed accurately alongside manual confirmations; internal status codes are unchanged.

Files created: `_bank_example_choice.html` and `static/js/bank-example-choice.js`. Files modified: the two review templates, shared review header/filter macros, WHO/WHY modal label/cache version, WHO/WHY selection labels and asynchronous import-status wording. The current web-research proposal WHO field is displayed correctly. No backend or database schema change.

Verification: Jinja parsing, JavaScript syntax checks, live rendering and read-only opening of both example choices and the manual picker. Deployment creates a database/source backup and compares all existing data before and after installation. Financial records and rules are not reapplied.

The conversation shows the selected example description, uses shorter prompts, and provides a same-origin return-to-movement link. Manual buttons and example choices have explicit non-wrapping widths and comfortable click areas. The photo/rule conversation template and script are modified only to display this context and navigation.
