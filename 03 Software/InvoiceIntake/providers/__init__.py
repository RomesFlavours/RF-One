"""Provider-agnostic extraction boundary for Invoice Intake
(CROSS_DOMAIN_INVOICE_INTAKE_AGENT_001_FOUNDATION_V1).

See `base.py` for the Invoice Source Contract / NormalizedInvoice shapes,
`tesseract_provider.py` for the existing local OCR path wrapped behind this
boundary, and `textract_provider.py` for the new AWS Textract AnalyzeExpense
provider. Nothing in this package calls Purchasing, writes
PurchaseDocument/PurchaseLine, or is wired into `app.py`'s existing
upload/save routes — see the task report for why.
"""
