# Payroll Handoff Connector

**Version:** 0.1
**Status:** Draft — canonical boundary concept (Product Owner decision)
**Module:** Domain / Personnel Management (Cross Domain) / Compensation

---

## What this document is

This document canonicalizes the **Payroll Handoff Connector** — the boundary between RF-One Compensation and external Payroll execution. It is a **conceptual/functional** definition only: not a database specification, not an API specification, not a UI specification, not an ADP/Check/Gusto integration specification. It does not select, design, or implement any specific Connector.

---

## Canonical process boundary

```text
SOURCE FACTS / DOMAIN VALUES
        ↓
COMPENSATION
        ↓
APPROVED COMPENSATION DATA
        ↓
PAYROLL HANDOFF CONNECTOR
        ↓
PAYROLL PROVIDER / ACCOUNTANT
        ↓
PAYROLL PROCESSING
        ↓
PAYROLL RESULT
        ↓
optional Connector return / manual recording
        ↓
RF-One RECONCILIATION
```

RF-One owns everything only through **Approved Compensation Data**. RF-One does **not** own the statutory Payroll process.

---

## What the Connector is

The Payroll Handoff Connector is the boundary object/role responsible for:

- receiving Approved Compensation Data from RF-One;
- mapping/presenting/transporting those approved values in the form required by the selected Payroll Provider;
- delivering those values to the Payroll Provider;
- optionally receiving or recording the Payroll Provider's result, for RF-One's own reconciliation.

## What the Connector is NOT

The Connector does **not**:

- decide compensation amounts;
- calculate Payroll;
- determine tax withholding;
- calculate statutory taxes;
- perform payroll filing;
- change RF-One's approved economic values;
- make business decisions.

---

## The Connector may be automated OR manual — both are equally valid

The Connector **MAY** be:

- an automated API integration;
- a structured file export/import;
- CSV / SFTP;
- another machine-to-machine mechanism;
- a **manual human process**.

**A human operator entering RF-One's approved values into ADP or another Payroll Provider is a valid Connector implementation.** The functional boundary must work identically whether the Connector is automated or manual. Do not assume, require, or design around the Connector having an API — automation is optional, not architecturally required for the model to be valid.

### Human Connector example

RF-One calculates/prepares, for the relevant Pay Period:

```text
Person: Mario
Regular Hours: 40
Tips: 600
Incentive: 150
Tip Credit Make-Up: 0
```

Compensation is **APPROVED** (Approved Compensation Snapshot created).

A human payroll operator opens the approved RF-One Compensation data and enters the corresponding values into ADP.

```text
RF-One  = Compensation source
Human   = Payroll Handoff Connector
ADP     = Payroll Provider
```

The architecture is still valid. **No API is required** for the conceptual model to work.

---

## The Connector transports/maps — it never recalculates

The Connector may transform **format** (e.g. mapping an RF-One compensation component to a provider-specific earning code). It may never transform the **value**.

```text
RF-One:
  TIP_CREDIT_MAKEUP = 40.80

Connector:
  maps that to ADP earning code XYZ

40.80 remains 40.80.
```

The Connector cannot independently decide that it should be 35.00 or 50.00. Mapping an RF-One Compensation component to a provider-specific earning code is a **mapping concern**, never a **recalculation concern**.

---

## Payroll Provider / Accountant

The Payroll Provider (or Accountant) owns downstream Payroll execution. Examples **may** include ADP, another payroll service, an accountant using payroll software, or embedded payroll infrastructure — these are examples only; **no provider is canonical to RF-One**.

The Payroll Provider is responsible for activities such as:

- payroll processing;
- statutory payroll treatment;
- federal/state/local tax calculations;
- withholding;
- statutory deductions;
- employer payroll taxes;
- filings;
- tax remittances;
- W-2/W-3;
- applicable unemployment filings;
- direct deposit / ACH / other money movement;
- other provider-owned payroll compliance functions.

RF-One supplies the correct approved **values**. The Provider applies Payroll **treatment**.

---

## Relationship to `Administration/Payroll`

`01 Domains/Cross Domain/Administration/Payroll/` records what the external Payroll Provider actually did — the administrative execution/recording boundary, downstream of the Connector. The Connector itself (the handoff mechanism) and the Provider's result (what `Administration/Payroll` records) are distinct: the Connector transports Approved Compensation Data outward; `Administration/Payroll` records what came back. Neither the Connector nor `Administration/Payroll` decides compensation amounts.

---

## Related documents

- [README.md](README.md) — Compensation module purpose and boundary
- [COMPENSATION_AND_INCOME_COMPOSITION_001.md](COMPENSATION_AND_INCOME_COMPOSITION_001.md) §22 — Payroll Provider boundary within the functional specification
- [../../Administration/Payroll/README.md](../../Administration/Payroll/README.md) — the administrative execution/recording boundary downstream of the Connector
