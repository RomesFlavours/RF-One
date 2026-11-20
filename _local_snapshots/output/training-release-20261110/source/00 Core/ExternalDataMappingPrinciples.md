# External Data Mapping Principles

## Purpose

This document defines the principles governing how RF-One acquires and transforms data from external systems.

External systems are data sources, not business models.

RF-One always models the real business domain, regardless of how external systems organize or expose their data.

---

# Principle 1 – Domain First

The RF-One Domain Model has priority over every external data source.

External systems must adapt to the RF-One Domain.

The RF-One Domain must never adapt to external systems.

---

# Principle 2 – Source Records

Data received from external systems are called Source Records.

Source Records represent exactly what an external system provides.

They are never modified.

---

# Principle 3 – Business Meaning

Every Source Record must be interpreted according to its business meaning.

The Mapping Layer is responsible for translating external data into RF-One business concepts.

---

# Principle 4 – Conceptual Independence

External systems may contain:

- conceptual mistakes;
- implementation shortcuts;
- duplicated information;
- missing information;
- historical inconsistencies.

These characteristics must never become part of the RF-One Domain.

---

# Principle 5 – Traceability

Every business object created from external data must preserve a reference to its original Source Record.

This guarantees complete traceability.

---

# Principle 6 – Mapping Layer

Every external data source must pass through a Mapping Layer before entering the RF-One Domain.

The Mapping Layer is responsible for:

- interpreting external records;
- correcting conceptual inconsistencies;
- normalizing data;
- preserving traceability.

---

# Principle 7 – Stable Domain

Changes in external APIs must affect only the Mapping Layer.

The RF-One Domain Model must remain stable.