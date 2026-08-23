# Unit Of Measure

## Purpose

A Unit Of Measure defines the standardized unit used to quantify Items.

It provides a consistent measurement system across the entire platform, ensuring accuracy, interoperability and analytical consistency.

The same Unit Of Measure may be referenced by multiple Items.

---

# Responsibilities

A Unit Of Measure is responsible for:

- defining a standardized measurement unit
- providing a standard abbreviation
- identifying the measurement type
- supporting quantity validation

A Unit Of Measure never defines:

- Item identity
- prices
- inventory quantities
- purchasing
- recipes
- sales transactions

Those responsibilities belong to specialized entities and domains.

---

# Typical Attributes

- Unit Id
- Name
- Symbol
- Measurement Type
- Description
- Status
- Created At
- Updated At

---

# Measurement Types

Examples include:

### Mass

- Gram (g)
- Kilogram (kg)
- Milligram (mg)

### Volume

- Milliliter (ml)
- Liter (L)

### Length

- Millimeter (mm)
- Centimeter (cm)
- Meter (m)

### Quantity

- Each (ea)
- Piece (pc)
- Pack
- Box
- Case
- Bottle
- Can

### Time

- Second
- Minute
- Hour
- Day

---

# Relationships

Unit Of Measure

↓

Items

---

# Design Principles

A Unit Of Measure defines only a standardized measurement unit.

Business logic belongs to specialized domains.

---

# Benefits

Unit Of Measure provides:

- measurement consistency
- standardized integrations
- accurate calculations
- simplified reporting
- AI-friendly data normalization

---

# Multi Domain

Unit Of Measure belongs to the Commercial Catalogue domain.

It is shared by Purchasing, Inventory, Production, Recipes, Sales, Retail, Hospitality and future business domains.