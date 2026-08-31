# Exclusions

**Version:** 1.0
**Status:** Approved
**Module:** Restaurant Domain / Server Performance
**Origin:** TASK_SERVER_PERFORMANCE_001

---

## Purpose

This document states explicit boundaries Server Performance (and its sibling module [Service Copilot](../Service%20Copilot/README.md)) must never cross, to prevent scope creep into modules this task does not own or redesign.

---

## Table assignment is outside this module

Server Performance and Service Copilot are never responsible for table/floor assignment. The Restaurant already uses a separate, proven method for distributing guests among Servers.

[Concurrent Service Load](Concurrent%20Service%20Load.md) is an **input/context variable** for Performance. It does **not** authorize this module to decide:

- which Server receives the next table;
- floor rotation;
- section assignment;
- host seating decisions.

This boundary is explicit and non-negotiable within this module's scope.

## Floor optimization is outside this module

For the same reason, no floor-optimization, staffing-level, or scheduling-recommendation capability is defined by this module. Concurrent Service Load is observed, not used to redistribute work.

## Payroll is outside this module

Server Performance's economic-motivation estimates ([Coaching Model.md](Coaching%20Model.md), "Personal Economic Benefit") are illustrative coaching content only — potential additional Tip dollars presented to the Server as motivation. They are **never** a Payroll input, never reconciled against actual payroll figures, and never touch `01 Domains/Administration/Payroll/` or its `payment_execution_provider`/Mercury/ADP concepts in any way. Server Performance does not read from, or write to, Payroll.

## Generic HR is outside this module

Server Performance does not model employment contracts, disciplinary procedures, leave, benefits, or any other generic HR concern. Where it touches personnel-decision-adjacent territory (persistent underperformance evidence — [Coaching Model.md](Coaching%20Model.md), "Underperformance / management evidence"), it only ever supplies evidence; the Decision itself belongs exclusively to Personnel Management's [Personnel Decisions](../../Personnel%20Management/Personnel%20Decisions/README.md) module, applied by a human.

## No unsupported personal-cause inference

RF-One does not infer unsupported psychological, health, relationship, hormonal, emotional, or personal causes for observed performance variation. Performance may be affected by innumerable personal or contextual factors RF-One cannot reliably know; where a cause is genuinely unknown, it remains an Unknown ([Evidence Sources.md](Evidence%20Sources.md)), never a fabricated explanation.

## Judgment / Customer Reading is future-only

`Judgment / Customer Reading` (a Server's skill at interpreting a table and deciding when to pursue, modify, or stop an approach) is explicitly documented as future development, not implemented by this task — see [Future Development.md](Future%20Development.md).

## No software, models, or schema

This module is Domain/conceptual architecture documentation only. It defines no database schema, no calculation code, no AI/recommendation model, no survey, no mobile/smartwatch application, no OpenTable/Resy integration, no Training software, and no table-assignment logic. All of these are future Product/Runtime/Software work, to be built against this Domain specification once commissioned.

---

## Related documents

- [Server Performance.md](Server%20Performance.md)
- [Concurrent Service Load.md](Concurrent%20Service%20Load.md)
- [Future Development.md](Future%20Development.md)
- [../../Personnel Management/Personnel Decisions/README.md](../../Personnel%20Management/Personnel%20Decisions/README.md)
- [../../Administration/Payroll/README.md](../../Administration/Payroll/README.md)
