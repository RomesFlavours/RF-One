# RF-One Strategy

**Version:** 1.0
**Status:** Approved
**Module:** Strategy

---

## Related documents

- [01_Economic_Value_and_Measurement.md](01_Economic_Value_and_Measurement.md)
- [02_Service_Delivery_and_Knowledge_Advantage.md](02_Service_Delivery_and_Knowledge_Advantage.md)
- [03_Shared_Intelligence_and_Knowledge_Governance.md](03_Shared_Intelligence_and_Knowledge_Governance.md)
- [README.md](README.md) — layer authority and scope
- See also [../00 Core/ConceptualArchitecture/00_RF-One_Core_Vision.md](../00%20Core/ConceptualArchitecture/00_RF-One_Core_Vision.md) and [../00 Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md](../00%20Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md).

---

## Purpose

This document is the entry point of RF-One's company/product strategy. It states RF-One's commercial orientation as a business, and points to the detailed strategy documents that specialize it.

This is **strategy**, not ontology: it explains what RF-One as a company chooses to prioritize commercially. It does not redefine any universal Core concept, and it is not itself a Product specification.

---

## 1. Layer separation

`09 Strategy/` is authoritative for **RF-One's own company/product-business strategy**.

It is **not** authoritative for:

- universal Core ontology (`00 Core/`);
- Domain semantics (`01 Domains/`);
- specific Product configuration (`02 Products/`);
- Runtime implementation (`03 Software/`).

**Where Strategy conflicts with Core semantics, Core wins for conceptual meaning.** A commercial priority stated here (for example, that RF-One aims to create measurable economic value) is a strategic choice of RF-One as a business — it is never a claim about what every Subject the Core models must want, and it must never be read back into Core as ontology.

**Where Product implementation differs from Strategy, the discrepancy must be visible** rather than silently redefining Strategy to match what a given Product happens to do. A Product may legitimately diverge from a stated strategic preference for good reason; when it does, that divergence should be documented at the Product level, not absorbed silently into this layer.

---

## 2. RF-One is business-first

RF-One's Core is domain-independent and may in principle apply to non-business Subjects and Domains (see [../00 Core/ConceptualArchitecture/00_RF-One_Core_Vision.md](../00%20Core/ConceptualArchitecture/00_RF-One_Core_Vision.md)). Commercially, however, RF-One's priority is **B2B business value**: RF-One as a company builds and sells Products that must create measurable economic value for the businesses that use them.

This commercial priority is **not** universal Core ontology. It does not imply that every Subject the Core can model is a business, or that every Desire or Goal the Core can represent must be economic. It is the commercial lens through which RF-One, the company, currently chooses to build Products.

---

## 3. Business Autopilot as commercial direction

RF-One's Core already defines the Business Autopilot operating model — RF-One may make and execute Decisions within explicitly Delegated Authority, while the Subject retains ultimate sovereignty over direction (see [../00 Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md](../00%20Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md)).

Strategically, this is not merely recommendation software. The commercial direction is that, within Delegated Authority, RF-One Products should increasingly observe, interpret, detect problems and opportunities, decide, execute, measure Outcomes, learn, correct course, and escalate when required — reducing the operational burden on the Pilot without reducing their command. Human control does not imply continuous human operation.

This section does not duplicate the Core definition of Business Autopilot; it states why that operating model is commercially central: a Product that only recommends captures less value, and requires more customer effort to realize any value, than one that is trusted to act within a boundary the customer has knowingly set.

---

## 4. Economic value orientation

RF-One commercial Products should aim to create measurable economic value for business customers. This is a central commercial objective, not a universal Core Goal — see [01_Economic_Value_and_Measurement.md](01_Economic_Value_and_Measurement.md) for the full treatment, including why "Maximize Economic Profit" is not Core ontology, how value may be measured, and the epistemic safeguards required when doing so.

---

## 5. Broad but bounded optimization scope

RF-One may optimize across any business area for which it has relevant Domain knowledge, sufficient Reality information, compatible confirmed Goals, Delegated Authority, applicable Constraints, acceptable risk, and legal/policy permission.

This scope is intentionally **not** described as unlimited: it is bounded by what RF-One actually knows, is authorized to do, and is permitted to do. The breadth of optimization is expected to expand as RF-One gains valid knowledge and authority — it is not fixed at the boundary of a single business area, and it is not restricted by this document to any specific list of areas.

RF-One must never override a customer's confirmed Goals in pursuit of economic value; see Subject Sovereignty in [../00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](../00%20Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md).

---

## 6. Operational and strategic horizons

RF-One should reason across multiple economic time horizons, recognizing at minimum an **operational horizon** (near-term, measurable soon after action) and a **strategic horizon** (longer-term initiatives whose acceptable return period depends on the specific strategy). Short-term optimization must not silently destroy long-term value. See [01_Economic_Value_and_Measurement.md](01_Economic_Value_and_Measurement.md) for detail. This two-horizon framing is a minimum, not a rigid ceiling — more granular horizons may be introduced later where useful.

---

## 7. Current strategic priorities

- Establish RF-One as a **Business Knowledge Platform**, not a commodity software product — see [02_Service_Delivery_and_Knowledge_Advantage.md](02_Service_Delivery_and_Knowledge_Advantage.md).
- Prefer centralized/service delivery where it best protects and compounds RF-One's accumulated knowledge advantage, as a current strategic preference rather than an immutable law — see [02_Service_Delivery_and_Knowledge_Advantage.md](02_Service_Delivery_and_Knowledge_Advantage.md).
- Pursue the long-term opportunity of shared, generalized knowledge across deployments, under strict governance that never treats customer-specific knowledge as automatically shareable — see [03_Shared_Intelligence_and_Knowledge_Governance.md](03_Shared_Intelligence_and_Knowledge_Governance.md).
- Demonstrate B2B return on investment through defensible, epistemically honest value measurement — see [01_Economic_Value_and_Measurement.md](01_Economic_Value_and_Measurement.md).

This document does not specify a Product roadmap, pricing, go-to-market plan, or delivery architecture; those belong to `02 Products/` and `03 Software/` respectively once defined.
