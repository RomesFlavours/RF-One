# Person Organizational Applicability — Shared Directory Contract

**Version:** 1.0  
**Status:** Approved functional rule — Product Owner decision, 2026-11-03.  
**Scope:** All RF-One Domains, modules and shared services. This document does not create a new Domain or assert that every runtime already implements the rule.

## Single source of truth

Organizational applicability is selected and maintained exclusively in the shared
Employee Directory (Anagrafica). Every consuming Domain, module and service must
read and validate that applicability through the shared Directory services.
Consumers must not maintain independently editable copies, introduce their own
applicability configuration, or reconstruct applicability from their local data.

The person has one canonical identity. Working in several organizational units
does not create several person identities. Existing role and assignment concepts
must be reused where appropriate rather than duplicated in a parallel roster.

## Explicit applicability

The Directory must represent these alternatives explicitly:

| Applicability | Restaurant example |
|---|---|
| One organizational unit | A server or executive working for one restaurant |
| Several organizational units | A server working for two or more restaurants in the group |
| The entire group | An executive working for the whole restaurant group |

The same contract applies to other Business Domains using their organizational
units; restaurants are examples, not a dependency of the shared model.

Group-wide applicability is an explicit configured scope. It is not equivalent
to a missing unit, an empty selection, unknown applicability, or a list of units
guessed by a consumer. A person with group-wide applicability must not be excluded
merely because they lack an individual restaurant assignment or a Clover record.

Unconfigured applicability must remain distinguishable from group-wide
applicability. It never silently grants all-unit scope. Concrete storage fields
and API encodings must preserve these distinctions; this document does not
prescribe a database representation.

## Applicability, active status and access are distinct

Organizational applicability describes where the person's work or responsibility
applies. Active employment status describes whether the person is currently an
eligible employee. Authorization describes what an account may see or do.

Consumers must use the shared applicability and lifecycle rules, then enforce
the permissions required by their operation. Applicability alone does not grant
access, and working in the same restaurant does not itself authorize an action
on another person. An active account is not proof of active employment.

In particular, a module must not invent a rule such as "only colleagues at the
requester's workplace" as a substitute for the shared contract and explicit
authorization. An owner exception that preserves administrative access does not
make a dismissed employee eligible for a new employee selection.

## Consumer obligations

All employee selectors and new employee-related actions must:

1. Resolve the canonical person and obtain applicability from the shared Directory.
2. Use shared active-status checks for new operational employee selections, without
   replacing them with account status or raw source presence.
3. Apply the operation's explicit authorization on the server; form parameters
   cannot widen scope. Missing authorization context must not default to all units.
4. Revalidate current eligibility and applicability before creating or sending a
   new request, including when a previously rendered form or a retired alias is used.
5. Preserve historical records and their original context when applicability or
   employment changes. Historical consultation remains subject to access controls;
   it must not make a dismissed person selectable for a new operational action.

Interviews, Selection, Training, Bank, Tips, Projects and every other consumer are
subject to this same contract. Their specialist business rules remain their own;
the Directory supplies the common applicability facts and checks, not the outcome
of a selection, assessment, allocation or professional decision.

## Verification scenarios

- A server applicable to one restaurant and a server applicable to several are
  resolved from the same Directory, with no per-module reconfiguration.
- An executive applicable to one restaurant and an executive applicable to the
  entire group retain those distinct, explicitly configured scopes.
- Group-wide applicability works without an inferred restaurant or POS identity;
  unconfigured applicability is never interpreted as group-wide.
- Every consumer reads the same authoritative applicability; a stale form or
  manipulated identifier cannot bypass current shared checks or authorization.
- Dismissal prevents new operational employee selections while historical
  interviews, assignments and other records remain available to authorized users.

## Related documents

- [Domain Architecture](../Domain%20Architecture.md) — cross-Domain adoption.
- [Person Continuity](PERSON_CONTINUITY_001.md) — canonical identity and historical continuity.
- [Employee Registry](../Business%20Domain/Restaurant/Organization/Employee%20Registry.md) — existing Restaurant registry and assignment integration.
- [Common Interview Service](INTERVIEW_SERVICE_001.md) — one consumer of this contract.

Implementation, migration and release validation must be recorded separately.
Approval of this rule is not evidence of a completed integration or AWS release.
