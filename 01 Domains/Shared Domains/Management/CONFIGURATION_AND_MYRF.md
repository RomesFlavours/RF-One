# Management Configuration and MyRF

**Status:** P01 draft configuration proposal, with M03's narrower reported-agreed MyRF output.  
**Sources:** P01 §§4, 7.2, 8, 9–12; M03 §§6–7, 10; R06.

## Management Configuration

P01 §11 proposes a dedicated configuration page for access profiles/enabled sub-areas, validation responsibilities, visibility rules, coaching modes/limits, temporal relevance parameters, operational authorizations and emergency-suspendable functions.

These are functional needs. Existing system Identity & Access remains the owner of account/authority mechanisms. Do not create a separate authorization registry or change its structurally frozen foundation. Exact mapping of configuration to existing authority, scope and auditing is open (G04, G14).

## Admin and emergency delegate

P01 §§11.1–11.2 proposes **one Management Admin account**, authorized to change Management configuration. Hierarchical seniority does not automatically confer Admin privilege.

The Admin can designate an emergency delegate whose only power is selective suspension of People/MyRF functions previously authorized by Admin. The delegate cannot change configuration/authorizations/RFCore, enable undelegated functions or independently reactivate suspended functions. Reactivation is reserved to Admin; interventions are recorded and notified.

No Admin identity, delegate identity, actual permissions, notification recipients, recovery route, suspension catalogue or continuity behavior is established by this draft. “One Admin” is Management scope, not a replacement for system account administration. Do not grant any role from this document alone.

## Validator and visibility

P01 §8 names Shelbi as initial development validator and makes the responsibility configurable. Treat that designation as **PROPOSED** within P01's overall draft status, not an account grant or approval authority over all Management.

Admin, validator, manager and observation contributor are distinct responsibilities. None gets access to original People observations or authors by virtue of the role (P01 §6.1). Access to a sub-area is not access to all its data (§4). Organization interview confidentiality has a different source contract; do not combine the two.

## MyRF

M03 §6 reports agreement on an initial personal list of assigned processes/projects, with the ability to continue AI-guided work. Assignment approval and plan approval remain distinct. P01 §10 describes People adapting explanations, contextual coaching and understanding checks through MyRF across Management, Bank, Purchasing and other domains. Under the approved People–Cognito boundary (D07; [People §2](People/README.md)), People decides which professional support is pertinent and Cognito delivers the interaction; the rest of P01 §10 remains a proposal.

Exact personal views, profile summaries, recipients, access rights, coaching availability, feedback and reporting cadence remain undefined. Information crossing domains is necessary/authorized only. No UI prototype, navigation, public profile or notification delivery is specified by this package.

## Communication

M03 §6 links daily morning/evening lead briefs, urgent calls and **INFO, DECISION, BLOCKER** tags to a possible communication agreement/integration. M03 §10 still requests confirmation. This is not a fourth Management module, not a built integration and not permission to send messages.
