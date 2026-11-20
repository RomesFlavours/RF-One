# Bank Historic Source Corpus — Inventory

**Date:** 2026-09-22
**Source location:** `Bank/Historic Data/` (git-ignored — see §1)
**Mode:** READ-ONLY. No source file was renamed, moved, modified, normalized
in place or deleted. Every SHA-256 below is taken over the original bytes.

> **Safe metadata only.** This report carries relative paths, source types,
> dates, row counts, SHA-256 and last-four identity. It contains **no full
> bank or card account number**, and none may ever be added to it.

---

## 1. Location and git safety

The Product Owner's brief named `Bank/Historical Data/`. The directory that
exists on disk is **`Bank/Historic Data/`** (no "-al"). No directory named
`Bank/Historical Data/` exists. This report uses the real path.

| Check | Result |
|---|---|
| Files found (recursive) | **23**, all in the single top-level directory — no subfolders |
| `git check-ignore` covers every file | **23 / 23**, via `.gitignore:106 → /Bank/` |
| Files tracked under `Bank/` | **0** |
| Visible to `git status --untracked-files=all` | **none** |

The directory is fully git-ignored. No raw source file is, or can be
accidentally, committed.

---

## 2. Corpus at a glance

| Source family | Files | Institution | Format(s) |
|---|---|---|---|
| Chase bank account activity | 6 | Chase | CSV (`Details, Posting Date, Description, Amount, Type, Balance, Check or Slip #`) |
| Chase credit card activity | 6 | Chase | CSV (`Card?, Transaction Date, Post Date, Description, Category, Type, Amount, Memo`) |
| First Citizens account history | 1 | First Citizens | CSV (`Account Number, Post Date, Check, Description, Debit, Credit, Status, Balance`) |
| American Express activity | 8 | American Express | 4 × XLSX, 3 × QBO/OFX, 1 × CSV |
| Zelle Payment Activity | 1 | Chase (QuickPay) | PDF, **no text layer** (§6) |

**Five distinct source formats across three institutions.** Amex alone
arrives in three mutually different formats.

---

## 3. File inventory

Row counts are data rows, excluding the header. Dates are the min/max of the
file's own primary date column.

| File | Type | Rows | From | To | ··last4 |
|---|---|---:|---|---|---|
| `AccountHistory (1).csv` | First Citizens account | 7 890 | 2018-12-10 | 2026-09-21 | ··7470 |
| `Chase3376_Activity_20260922.csv` | Chase bank account | 1 504 | 2025-12-30 | 2026-09-22 | ··3376 |
| `Chase2915_Activity_20260922.csv` | Chase credit card | 1 065 | 2024-09-20 | 2026-09-17 | ··2915 |
| `Chase3583_Activity_20260922.csv` | Chase bank account | 545 | 2024-09-26 | 2026-09-21 | ··3583 |
| `Chase1562_Activity_20260922.csv` | Chase credit card | 399 | 2024-09-22 | 2026-09-20 | ··1562 |
| `Chase9318_Activity_20260922.csv` | Chase bank account | 269 | 2024-10-01 | 2026-09-14 | ··9318 |
| `Chase1057_Activity_20260922.csv` | Chase credit card | 136 | 2025-10-20 | 2026-09-03 | ··1057 |
| `Chase1057_Activity_20260922 (1).csv` | Chase credit card | 136 | 2025-10-20 | 2026-09-03 | ··1057 |
| `Chase0336_Activity_20260922.csv` | Chase bank account | 61 | 2026-03-25 | 2026-09-21 | ··0336 |
| `Chase3144_Activity_20260922 (1).csv` | Chase credit card | 52 | 2026-04-19 | 2026-09-15 | ··3144 |
| `Chase3144_Activity_20260922.csv` | Chase credit card | 14 | 2026-09-11 | 2026-09-18 | ··3144 |
| `Chase8076_Activity_20260922.csv` | Chase credit card | 11 | 2026-08-21 | 2026-09-17 | ··8076 |
| `Chase7129_Activity_20260922.csv` | Chase bank account | 43 | 2024-09-27 | 2026-08-31 | ··7129 |
| `Chase0214_Activity_20260922.csv` | Chase bank account | 7 | 2026-08-20 | 2026-09-16 | ··0214 |
| `Amex.csv` | Amex activity (CSV) | 94 | 2026-03-01 | 2026-03-31 | ··1002 |
| `Amex (2).xlsx` | Amex activity (XLSX) | 89 | 2025-09-01 | 2025-09-30 | ··1002 |
| `Amex.qbo` | Amex activity (QBO) | 70 | 2025-08-01 | 2025-08-31 | ··1002 |
| `Amex.xlsx` | Amex activity (XLSX) | 64 | 2025-10-01 | 2025-10-31 | ··1002 |
| `Amex-activity.qbo` | Amex activity (QBO) | 54 | 2026-01-01 | 2026-01-31 | ··1002 |
| `Amex  activity.xlsx` | Amex activity (XLSX) | 48 | 2025-12-01 | 2025-12-31 | ··1002 |
| `AmeActivity.xlsx` | Amex activity (XLSX) | 46 | 2025-11-01 | 2025-11-30 | ··1002 |
| `Amex (3).qbo` | Amex activity (QBO) | 45 | 2026-02-02 | 2026-02-28 | ··1002 |
| `Zelle 1-08.pdf` | Zelle Payment Activity | 41 pages | 2025-12-15 | 2026-09-29 | — |

`··1002` is Amex's own partial mask as it appears in the export, not a
truncation applied here.

---

## 4. Provenance — SHA-256 over original bytes

| File | Bytes | SHA-256 |
|---|---:|---|
| `AccountHistory (1).csv` | 759 341 | `3e35343e503dc6ea93d8de713bfee89c1e2fed981c390b2f9ebc6bc85d11f278` |
| `AmeActivity.xlsx` | 9 324 | `371835a8e9aa8303ec5d7646dbd0d3860d5d924d5c075a68dda84b71b523a00c` |
| `Amex  activity.xlsx` | 9 499 | `1b5ab75070f8753e2a965026b9d3e9031174133f2046477bcfee9fa7b684ca85` |
| `Amex (2).xlsx` | 20 394 | `e410e218457247315ad50a974c50d95fb6596c096f41482fdf3e0a502ab318c9` |
| `Amex (3).qbo` | 15 034 | `4f0501a8a110663d80c612a9904bae11611460e7978d18b32d480cc7f70bc6bd` |
| `Amex-activity.qbo` | 17 777 | `ddc9dd5f18699cf178eaea9995abef373f134c3103d8e953cc30af9fc4aa6229` |
| `Amex.csv` | 7 530 | `aff7569c0e05d7dd910b60ae4cbce8a8e8d5ef3c81b0a6ac0fdf819813e02114` |
| `Amex.qbo` | 22 871 | `941fb87b3970681acd5d0eba049a0fa7d512ee2c04ed8e8ec18700689a04fe9c` |
| `Amex.xlsx` | 11 281 | `dadbf3db35eab4c75f297b6bba47a044fc77ab97c5f248837651d341d7f3c1d8` |
| `Chase0214_Activity_20260922.csv` | 1 036 | `ce2e3431ea220726cf9ddf057b3c796cf2af369b10b35d796b15d17ed1e2ed1d` |
| `Chase0336_Activity_20260922.csv` | 10 972 | `3eb088e97d283721ffd2651afabf6ecab4e643c4e93ab3c6b8bd4f608e18c8cb` |
| `Chase1057_Activity_20260922 (1).csv` | 9 544 | `d252939a0e836d0d611256212d7c8b3eff6eb049d3f867ae831043475cf4c475` |
| `Chase1057_Activity_20260922.csv` | 10 229 | `e6af106acb90856a84aa90dbf9bff9b0a68cf13707a26c20c7def75a445a3d6e` |
| `Chase1562_Activity_20260922.csv` | 26 343 | `8a3d77e38ae3ffd1249f500841092e3f72d1dbb56c9b9be2f7daff9090de8409` |
| `Chase2915_Activity_20260922.csv` | 69 806 | `ccefde64bcd4dab3763a4cd470b09b833f09135b42b8aae21253ac2f94005eef` |
| `Chase3144_Activity_20260922 (1).csv` | 3 838 | `47f64f3306b97ac4689a48dbbfb2985d5ca02feb1e01fbcd5645da69e27d7767` |
| `Chase3144_Activity_20260922.csv` | 1 200 | `4096bcadeb6ded06406fe7c1c8a54d3dac6a8c494c0785da1e3d094255db4eb3` |
| `Chase3376_Activity_20260922.csv` | 328 405 | `3730541f8c5eb6d2acc84a92780e605096d2ecb2ec3a570f59b022317b4cd3ad` |
| `Chase3583_Activity_20260922.csv` | 93 622 | `2e8c21e2e2389cf010d49bb6adc38a8a8d5025987feaba1e65af4549bb0c573d` |
| `Chase7129_Activity_20260922.csv` | 3 262 | `68b5e7d7286804ab7b8ddcf206747664a95a87065af31099e912bdaec90ca1e7` |
| `Chase8076_Activity_20260922.csv` | 970 | `693c728aa5cbe0002e0dacec5a9a6a93f2dfb798ce01e92021a6ffed0bd3cd02` |
| `Chase9318_Activity_20260922.csv` | 28 062 | `5c649a865dbac0efd59661a3fc882206e0186aac8ad29e68777c428029d0bca8` |
| `Zelle 1-08.pdf` | 7 364 913 | `214e9507409f826188a1c5f1fb57f0c5b67a37cc98abaa12aba199da43e805ff` |

**No two files are byte-identical.** Every SHA-256 is distinct.

---

## 5. Duplicate and overlap analysis

Byte-distinct is not the same as content-distinct. The two `(1)` pairs were
compared line by line on their shared columns.

### `Chase1057` — a true duplicate

| | |
|---|---|
| Headers | differ: the plain file has a leading `Card` column, the `(1)` file does not |
| Rows | 136 in both |
| Lines in both | **136** |
| Lines only in one | **0** |

Same export, one with the `Card` column and one without. **One of the two is
redundant.** The plain file is the richer of the two.

### `Chase3144` — NOT a duplicate; two different windows

| | |
|---|---|
| Rows | 14 (plain) vs 52 (`(1)`) |
| Lines in both | **3** |
| Only in the 14-row file | **11** — the most recent, 2026-09-16 … 2026-09-18 |
| Only in the 52-row file | **49** — the older span, 2026-04-19 … 2026-09-15 |

Two partially overlapping exports of the same card. **Both are needed**; the
3 shared lines must be deduplicated, not double-counted.

**Consequence for ingestion:** file-level SHA-256 alone cannot detect either
case. Idempotency must be enforced at the **transaction line** level.

---

## 6. The Zelle PDF cannot be read as data — BLOCKER

`Zelle 1-08.pdf` is a browser print of `chase.com` Payment Activity
(`Producer: Microsoft: Print To PDF`, `Title: Payment Activity - chase.com`).

| Measure | Value across all 41 pages |
|---|---|
| Text characters | **0** |
| Embedded images | **0** |
| Vector curves | ~1 758 per page |
| Rectangles | ~170 per page, 138 of them under 3 pt wide |

The glyphs were converted to **vector outlines**. There is no text layer and
no image layer, so neither text extraction nor table extraction returns
anything. This is a property of the file, not of the tooling.

Rendering a page to an image confirms the content is present and legible to
a human. The document holds, among others, the Tips distributions labelled
`"26 Sep 14-20 Tip"` dated 2026-09-21 — directly related to the certified
Tips window.

**Date span (read visually, from the first and last pages):
2025-12-15 → 2026-09-29**, in descending order. The brief anticipated Zelle
history "from 2024 onward"; the file starts **2025-12-15**. Roughly two
years of the expected history are not in this file.

Only two routes exist, and the choice is the Product Owner's:

1. **A real export from Chase** (CSV/QBO/OFX of QuickPay activity) — exact,
   machine-readable, no transcription risk. Preferred.
2. **OCR of the 41 rendered pages** — feasible, but it would put
   *transcribed* figures into a financial system. Reconciliation data that
   has been read by a character recogniser is not a source of truth.

**No OCR was performed and no figure from this PDF was extracted into any
dataset.** Nothing is invented and nothing is estimated.

---

## 7. Coverage against the certified local Bank baseline

Cross-checked against the 14 Payment Instruments certified in
`BANK_LOCAL_BASELINE_MANIFEST.md`.

| ··last4 | Instrument | Legal Entity | Source files |
|---|---|---|---|
| ··7470 | WP-Checking | Angeli E Demoni, LLC | 1 |
| ··7129 | RF Saving | Angeli E Demoni, LLC | 1 |
| ··1057 | Business | Angeli E Demoni, LLC | 2 (duplicate pair) |
| ··3336 | RFWP- Checking | Angeli E Demoni, LLC | **NONE** — see §8 |
| ··0336 | RFMD Checking | RF Mount Dora, LLC | 1 |
| ··8076 | Ink Unlimited | RF Mount Dora, LLC | 1 |
| ··3583 | RF Corporate | RF Gelati, LLC | 1 |
| ··3144 | Ink Giovanna | RF Gelati, LLC | 2 (complementary) |
| ··2270 | Business Anthony | RF Gelati, LLC | **NONE** — see §9 |
| ··9318 | Pino Checking | *(none — personal)* | 1 |
| ··0214 | Ceo Checking | *(none — personal)* | 1 |
| ··1562 | Sapphire | *(none — personal)* | 1 |
| ··2915 | Freedom | *(none — personal)* | 1 |
| *(no last four)* | Chase-2915 *(INACTIVE, historical)* | *(none)* | **NONE** |

**11 of 14 instruments are covered. 3 are not.**

Present in the source but **absent from the baseline**:

| ··last4 | Files | Observation |
|---|---|---|
| ··3376 | `Chase3376_Activity_20260922.csv` | 1 504 rows — the largest Chase file in the corpus |
| ··1002 | 8 Amex files | **American Express is not represented in the baseline at all** — the 14 certified instruments are Chase and First Citizens only |

---

## 8. OPEN QUESTION — ··3376 and ··3336

These are the observed facts, kept separate from any interpretation:

- The baseline holds `RFWP- Checking` with `last_four = '3336'` and an
  **empty** `external_account_identifier` — there is no full number in the
  database to corroborate it. The value was hand-entered into the legacy QA
  database on 2026-09-20.
- The corpus holds `Chase3376_Activity_20260922.csv`, named by Chase's own
  export convention, which derives the digits from the real account.
- `Bank/Download/` holds `Chase3376_Activity_20260915.csv` — the **same
  ··3376 identity from a second, independent export a week earlier**.
- The ··3376 transactions name `ANGELI E DEMONI LLC` (89×), `ROME'S FLAVOURS`
  (59×) and `GIUSEPPE MIRAGLIA` (64×) — consistent with the Winter Park
  operating account, which is what `RFWP- Checking` is.
- No source file for ··3336 exists in either directory.

**Interpretation (not a decision):** the two readings are (a) the baseline's
`3336` is a transposition of `3376`, so they are one account, or (b) they are
genuinely two different Chase accounts. The evidence leans to (a), because a
bank-generated filename is stronger evidence than a hand-typed field, and
because it appears twice independently. **This report does not resolve it.**

**The Product Owner must confirm which is correct.** Until then no ··3376
data may be attributed to `RFWP- Checking`, and the baseline's ··3336 must
not be silently rewritten.

---

## 9. Adjacent folder — `Bank/Download/` (not part of this scan)

Noted for completeness only; it was **not** scanned, parsed or ingested. It
sits inside the repository's `Bank/` directory and is equally git-ignored.

It holds 14 files, all dated 2026-09-15 — an earlier export of the same
accounts. It is relevant for one reason:

> It contains **`Chase2270_Activity_20260915.csv`**, the only known source
> for `Business Anthony ··2270`, which §7 records as missing.

It also contains `AccountHistory.csv` and `Chase3376_Activity_20260915.csv`.
Whether this earlier vintage should be promoted into `Bank/Historic Data/`
is a Product Owner decision; nothing was moved.

---

## 10. Historical depth and gaps

Within each instrument's own span, month coverage is **contiguous — zero
internal holes**. The differences are in where each span *starts*.

| ··last4 | Rows | First | Last | Months |
|---|---:|---|---|---:|
| ··7470 | 7 890 | 2018-12 | 2026-09 | 94 |
| ··2915 | 1 065 | 2024-09 | 2026-09 | 25 |
| ··1562 | 399 | 2024-09 | 2026-09 | 25 |
| ··3583 | 545 | 2024-09 | 2026-09 | 25 |
| ··7129 | 43 | 2024-09 | 2026-08 | 24 |
| ··9318 | 269 | 2024-10 | 2026-09 | 24 |
| ··1057 | 136 | 2025-10 | 2026-09 | 12 |
| ··3376 | 1 504 | 2025-12 | 2026-09 | 10 |
| ··1002 (Amex) | 510 | 2025-08 | **2026-03** | 8 |
| ··0336 | 61 | 2026-03 | 2026-09 | 7 |
| ··3144 | 66 | 2026-04 | 2026-09 | 6 |
| ··0214 | 7 | 2026-08 | 2026-09 | 2 |
| ··8076 | 11 | 2026-08 | 2026-09 | 2 |

Row totals for ··1057 and ··3144 are the sum across their two files and
therefore include the duplication described in §5.

Two observations:

- **First Citizens ··7470 reaches back to December 2018** — 94 contiguous
  months, by far the deepest history in the corpus.
- **Amex stops at 2026-03.** Six months (2026-04 … 2026-09) are missing
  while every Chase source runs to 2026-09. This is the one real gap
  relative to "today".

---

## 11. What was NOT done

No source file was renamed, moved, modified, normalized in place or deleted.
No duplicate was removed. No staging or extraction dataset was written. No
row was imported into any database. No OCR was run. No figure was inferred,
estimated or invented. `rfone.db` was opened **read-only** and is unchanged.
AWS was not contacted. `Bank/Download/` was listed but not parsed.

---

## 12. Decisions required from the Product Owner

1. **··3376 vs ··3336** (§8) — same account or two accounts? Blocks any
   ingestion of the largest Chase file in the corpus.
2. **The Zelle PDF** (§6) — request a real export from Chase, or authorise
   OCR knowing the transcription risk? Blocks all Zelle history.
3. **`Business Anthony ··2270`** (§7, §9) — promote the 2026-09-15 export
   from `Bank/Download/`, or obtain a fresh one?
4. **Amex ··1002** (§7) — American Express is absent from the certified
   baseline. Should it become a Payment Instrument, and under which Legal
   Entity?
5. **Amex 2026-04 … 2026-09** (§10) — obtain the six missing months?
6. **The `Chase1057` duplicate** (§5) — confirm the `(1)` file may be
   disregarded.
