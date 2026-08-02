# Configuration

## Purpose

This document defines the configurable behavior of the Purchasing Module.

Business Rules are fixed.

Configuration adapts the module to different restaurants without changing the Domain Model.

---

# General Principles

- Configuration never changes business concepts.
- Configuration never changes the Domain Model.
- Configuration only changes operational behavior.

---

# OCR

Configurable:

- OCR Provider
- Supported Languages
- Image Quality Threshold
- Automatic Rotation
- Confidence Threshold

---

# Artificial Intelligence

Configurable:

- AI Provider
- Mapping Confidence Threshold
- Automatic Suggestions
- Validation Queue Priority

Business authority always remains human.

---

# Units

Internal standard is always:

- Gram

Display units may be configured for users.

Examples:

- g
- kg
- oz
- lb
- ml
- l
- gallon

Display configuration never affects stored values.

---

# Currency

Configurable:

- Default Currency
- Exchange Rate Source
- Decimal Precision

Historical documents always preserve the original currency.

---

# Validation

Configurable:

- Severity thresholds
- Automatic assignment
- Notification rules
- Escalation rules

Validation behavior remains unchanged.

---

# Integrations

Configurable:

- Supplier APIs
- XML formats
- EDI formats
- OCR providers

Every integration must generate the same Purchase Document.

---

# User Preferences

Configurable:

- Language
- Date format
- Number format
- Dashboard preferences

Business data remains unchanged.

---

# Design Principles

- Configure behavior, not business rules.
- Preserve the Domain Model.
- Preserve historical data.
- Preserve supplier information.
- One canonical purchasing model for every configuration.
