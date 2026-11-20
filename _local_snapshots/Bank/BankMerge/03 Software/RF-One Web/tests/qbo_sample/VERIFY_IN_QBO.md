# Verifying the QBO sample in a QuickBooks Online test company

**Status: the QBO import has not been verified yet.** The file was generated and checked inside Bank only
(`CHECKS.md`). Nothing was imported into QuickBooks or sent to it.

## Files

| File | What it is |
|---|---|
| `AccountList_Sample_Co_LLC.csv` | The chart of accounts the sample uses. In the test company, create these six accounts with exactly these names and types. |
| `QBO_journal_entries_Sample_Co_LLC.csv` | The generated file, exactly as Bank lets you download it. It holds 6 journal entries and 13 lines. |
| `preview_Sample_Co_LLC.json` | The preview: what each movement would be through the API (Purchase, Deposit, Transfer). |
| `CHECKS.md` | The checks Bank ran on the file, with their outcomes. |

Rebuild the files with: `python "03 Software/RF-One Web/tests/build_qbo_sample.py"`. It uses a temporary database that is deleted afterwards.

## Procedure

Use a QBO **sandbox or test company**, never a real company's books.

1. **Set up the test company**
   - Create a US company.
   - Do **not** connect any bank feed.
   - Create the six accounts listed in `AccountList_Sample_Co_LLC.csv`, keeping the same name and type.
   - Turn off account numbers. Intuit's import expects account names only.
2. **Import the file**
   - Go to Settings ⚙ → Import data → Journal entries.
   - Upload `QBO_journal_entries_Sample_Co_LLC.csv`.
   - Map the columns:
     - Journal No → Journal No.
     - Journal Date → Journal Date. The format is MM/DD/YYYY. Intuit does not document the expected format, so check this mapping explicitly.
     - Account Name → Account.
     - Debits → Debits.
     - Credits → Credits.
     - Description → Description.
3. **Check the result** against the table below. Use Reports → Journal, and the account registers.

| Journal No | Movement | Expected entry | Register effect |
|---|---|---|---|
| RFB-1 | Simple expense | Dr Supplies 42.50 / Cr Chase Checking 1001 42.50 | One line −42.50 in the Checking register |
| RFB-6 | One card payment, two categories | Dr Supplies 60.00, Dr Cleaning 40.00 / Cr Ink Card 2001 100.00 | **One** line of 100.00 in the card register, not two |
| RFB-7 | Card refund | Dr Ink Card 2001 15.99 / Cr Supplies 15.99 | Card balance goes down by 15.99 |
| RFB-2 | Deposit | Dr Chase Checking 1001 250.00 / Cr Catering income 250.00 | One line +250.00 in Checking |
| RFB-3 | Own-account transfer | Dr Chase Savings 1002 500.00 / Cr Chase Checking 1001 500.00 | One entry, no expense or income |
| RFB-4 | Card payment | Dr Ink Card 2001 300.00 / Cr Chase Checking 1001 300.00 | One entry, no expense |

4. **Check the totals**
   - Profit & Loss: Supplies = 42.50 + 60.00 − 15.99 = **86.51**.
   - Cleaning = **40.00**.
   - Catering income = **250.00**.
   - Nothing on any other P&L account.
   - Checking moves by −42.50 + 250.00 − 500.00 − 300.00 = **−592.50**.
   - Savings moves by **+500.00**.
   - Card balance = 100.00 − 15.99 − 300.00 = **−215.99**. The −215.99 means the payment exceeded the charges: the card was overpaid.
5. **Import the same file again.** QBO should refuse the existing journal numbers, or warn about them, when "Warn if duplicate journal number is used" is on. Record what happens.
6. **Record the result in Bank.** On the Bank page, use **Imported in QuickBooks** if the import succeeded. Use **Not imported: withdraw** if it failed, and give the reason.

## What this procedure has to settle (not verified yet)

- Whether the import accepts the MM/DD/YYYY date and the column names as they are.
- Whether a description longer than the field limit is cut or refused.
- What QBO does when the same Journal No is imported a second time.
- **Bank feeds.** Intuit's official list of records that a downloaded bank transaction can be matched to does not include journal entries. So when a company's accounts are also on bank feeds, the feed items for movements imported through this file must be **excluded**, not added. If they are added, the same movement is recorded twice.
  - Bank refuses to generate the file until the person confirms they will be excluded.
  - Try it once in the test company: connect a feed or upload a statement, and look at what QBO suggests in Pending.
- **Vendor.** A journal entry has no payee. The vendor is not tracked in vendor or expense reports, nor for 1099. If that is needed, the movement has to go through the API as a Purchase with an EntityRef, which needs the QBO connection.
