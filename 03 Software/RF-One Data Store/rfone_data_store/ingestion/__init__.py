"""Source ingestion adapters for the RF-One canonical operational database.

Each source system (Clover today; a future POS tomorrow) gets its own
sub-package under here. No canonical ORM model (see `rfone_data_store.models`)
depends on anything in this package — the dependency runs one way only:
ingestion → canonical schema.
"""
