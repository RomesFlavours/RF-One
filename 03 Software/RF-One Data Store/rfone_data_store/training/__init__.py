"""RF-One Training (Shared Domain) — first operational version.

Business logic for the staff dish/wine "pill" learning feature lives here,
mirroring the existing `rfone_data_store/tips/` and `rfone_data_store/
selection/` convention (service modules operate on a `Session`; the web
layer — Flask routes/templates — lives separately, in `03 Software/
Training/`, which imports from this package exactly like `Tips/app.py` and
`Selection/app.py` already import from `rfone_data_store.tips`/
`rfone_data_store.selection`)."""
