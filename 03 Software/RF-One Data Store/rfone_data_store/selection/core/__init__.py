"""Selection Core — generic, industry-agnostic Resume Screening reasoning.

Nothing in this package may import from `..industry` or mention a
restaurant, FOH/BOH, or any other industry concept
(01 Domains/Shared Domains/Selection/ResumeScreening/README.md,
"Domain architecture").
Industry-specific classification (which roles are customer-facing, which
titles map to which normalized role, seniority ranking) is always supplied
by the caller as data/callables, never hard-coded here.
"""
