# Process

## Purpose

A Process describes all the knowledge required to consistently achieve a Goal, regardless of who or what executes it.

A Process includes both execution and the knowledge necessary to understand, teach, verify and continuously improve that execution.

## Relationship with Goal

Every Process exists only to achieve a Goal.

Without a Goal, a Process does not exist.

## Components

A Process may contain:

- Goal
- Inputs
- Activities
- Decisions
- Rationale (why)
- Approved Variants
- Contextual Variants
- Discouraged Variants
- Quality Checks
- Common Mistakes
- Training Notes
- Verification
- Feedback

## Recursive Decomposition

A Process may be recursively decomposed into sub-Processes to reach the level of detail required by a Domain or Runtime.

```text
Process
→ sub-Process
→ sub-Process
```

A lower-level Process remains a Process. Granularity alone does not create a fundamentally different class of thing, and decomposition does not require a separate universal Core type such as "Activity" — the Activities a Process is built from (see Components above) may themselves be full Processes when a Domain or Runtime chooses to model them at that level of detail.

Decomposing a Process is optional: a Domain or Runtime is not required to model every Process explicitly as a hierarchy, and this pattern does not by itself require any part of that hierarchy to be persisted.

## Phases of Execution

A Process's execution may progress, chronologically, through up to four fundamental phases:

```text
Planning
→ Scheduling / Programming
→ Management
→ Operations
```

- **Planning** — determining what is to be achieved and under what approach: the Goal, its intended treatment, and the governing rules, before any commitment is made.
- **Scheduling / Programming** — turning what was planned into commitments, assignments, timing, sequencing or operational readiness.
- **Management** — governing execution: allocating attention and resources, reacting to actual conditions, and keeping the Process within its Goal, rules and constraints.
- **Operations** — materially carrying out the work that produces the result.

This sequence describes the logical progression of organizational work. It is not a software taxonomy, a menu structure, or a mandatory subdivision into modules. A Process may include one, several, or all four phases, depending on its level of decomposition (see "Recursive Decomposition" above) and the Goal it serves; a Process is not required to formally contain all four.

None of these phases is defined by who or what performs it. Management, for example, does not mean "a human manager performs an action": within Delegated Authority, RF-One may itself perform governing activity that belongs to the Management phase, exactly as it may perform Planning, Scheduling/Programming or Operations activity within the same boundary. Where a Process is automated, autonomous execution may span one or more of these phases without a human separately triggering each one — see [ConceptualArchitecture/11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md](ConceptualArchitecture/11_Process_Autonomy_and_Exception_Driven_Human_Involvement.md).

### Not part of this sequence

Reporting, Administration, Analysis and Feedback are not chronological phases of this sequence. They observe, support, document, measure or influence the Process, but must not be artificially inserted into Planning → Scheduling/Programming → Management → Operations:

- **Reporting** describes what happened or is happening.
- **Administration** records, formalizes, or satisfies administrative requirements.
- **Analysis** interprets data and results.
- **Feedback** returns knowledge to the system and may influence Planning or another future phase (see Learning, [ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md](ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md)).

Legal, compliance, tax and other similar constraints do not automatically constitute separate phases of the Process. They enter the Process as rules, limits, conditions or obligations that the four phases above must respect (see "Optimization Boundaries" below). Administration must adapt to the operational Process; the Process must not be deformed to fit the structure of administrative, accounting or software systems.

## Optimization Boundaries

Optimization and execution of a Process must remain subordinate to the currently applicable combination of:

- consciously confirmed Subject direction;
- the active Goal(s) the Process serves;
- Constraints;
- Subject Sovereignty;
- Delegated Authority;
- applicable law/policy;
- known risk limits;
- relevant Reality.

See [ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md](ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md) and [ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md](ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md).

Efficiency or optimization must never silently override these higher-order boundaries. When multiple Goals, Constraints, risks or authority boundaries coexist, they do not reduce to a single rigid total ordering; reconciling them is itself part of the reasoning RF-One performs, not a fixed precedence list.

## Verification

Every Process must be objectively verifiable.

Verification may be performed through:

- Human observation
- Images
- Video
- Sensors
- Artificial Intelligence

## Artificial Intelligence

AI supports the Process by:

- explaining
- teaching
- observing
- verifying
- detecting deviations
- suggesting improvements

AI does not define the Process.

## Design Principles

- Every Process has a Goal.
- Execution and knowledge are inseparable.
- Every significant activity should explain both WHAT and WHY.
- Variants are part of the Process.
- Every Process must be verifiable.
- Training is an integral part of the Process.
- A Process is independent from its executor.
- Humans, AI systems and robots may execute the same Process.
- Execution may progress through Planning, Scheduling/Programming, Management and Operations; a Process need not formally contain all four.
- Reporting, Administration, Analysis and Feedback are not phases of that sequence.
