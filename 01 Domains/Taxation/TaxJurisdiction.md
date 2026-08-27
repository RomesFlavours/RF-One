# Tax Jurisdiction

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Module:** Domain / Taxation

---

## Purpose

**Tax Jurisdiction** is the governmental/legal tax authority context relevant to a given tax fact or [Tax Treatment](TaxTreatment.md) — the "who has the authority to impose or interpret a tax rule here" dimension of Taxation.

---

## Definition

A Tax Jurisdiction represents a specific governmental or legal authority (national, sub-national, local, or supranational) whose rules may impose a [Tax Obligation](TaxObligation.md), define a [Tax Treatment](TaxTreatment.md), or otherwise be relevant to a [Tax Position](TaxPosition.md).

Core does not encode any specific jurisdiction, jurisdiction taxonomy, or jurisdiction hierarchy (see [../../00 Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md](../../00%20Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md), Section 11). Concrete jurisdictions (e.g. a specific country, state, province, or municipality) are Domain/Runtime knowledge, supplied when needed — not defined here.

---

## Must be time-sensitive

A Tax Jurisdiction's rules, rates, and interpretations change over time. Any reference to a Tax Jurisdiction's rule must preserve the point in time (or period) that rule was, is, or is expected to be, in effect — consistent with [Temporal Coherence](../../00%20Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md). A current rule must never be assumed to have applied historically, and a historical rule must never be assumed to still apply.

---

## A Subject may have more than one jurisdiction

**Do not assume one Subject has only one Tax Jurisdiction.** A Subject may simultaneously be relevant to several Tax Jurisdictions — for example, a national and a sub-national authority at once, or multiple national jurisdictions where activity, residency, or a transaction crosses borders. Taxation must be able to represent multiple concurrently relevant Tax Jurisdictions for the same Subject, fact, or transaction, without forcing a single-jurisdiction simplification.

---

## What a Tax Jurisdiction is not

- It is not the Subject's Legal Entity structure itself — see [README.md](README.md), "Taxation ≠ Legal Entity Management". A Legal Entity may be *subject to* one or more Tax Jurisdictions; the Jurisdiction is the authority context, not the entity.
- It is not a fixed, closed taxonomy maintained by Core or by this Domain — see [../../00 Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md](../../00%20Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md), Section 11.

---

## Related concepts

- [TaxObligation.md](TaxObligation.md)
- [TaxTreatment.md](TaxTreatment.md)
- [TaxPosition.md](TaxPosition.md)
- [Taxation.md](Taxation.md)
- [../../00 Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md](../../00%20Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md)
