# Local Selection configuration

The Product Owner's updated scope (2026-11-14) is a Configurations tab with an
initially empty list of Positions of Work (PDL). A single modal creates and edits
one name. Show only Name and Edit in the list. Do not add availability controls,
usage counts, default entries or external integrations. Contextual help is a text
link opening a modal. Existing Selection administrator authorization, CSRF,
validation and concurrent-update protection remain in force.

The earlier seeded entries are removed from the visible catalogue through one
explicit local operation. Retain their internal historical identity for existing
operational Jobs, without making them choices for new Jobs. Initialization never
seeds entries and never clears names subsequently entered by the user. Existing
Job records, assessment data and AWS are unchanged. New catalogue entries use
stable internal codes; only their names are entered by the user.

The original AWS source archive is retained in output/awsselection-verification.
Italian UI remains selected by the official local launcher. User facts, identifiers,
API values and export schemas are not translated. The erroneous Google sharing
caption was a translation-catalogue error, not a sharing integration, and is removed.

## Expandable configuration blocks (2026-11-14)

Configurations contains Positions of Work and Application Page as separate
expandable blocks. Up/down arrows reorder whole blocks. Order and expansion
state persist in this browser's local storage, without changing business data.
Application Page moves out of Applications and retains the current Job context,
its public URL and Open/Closed/Draft instructions. With no selected Job, the
block asks the person to choose one in Selection.

## CV field reference picker (2026-11-14)

From the Requirements & Priorities rule-authoring dialog, open Fields extracted
from CV. The picker preserves the Product Owner's nine-area extraction table
verbatim, with separate single-field radio choices. Confirmation inserts an
area-qualified field reference at the draft caret without replacing existing
text, sending a message, saving a rule or changing the selected PDL/section.
Cancel, X and Escape discard the picker selection only. Contextual help preserves
the draft and selection. The picker identifies fields for the PDL rule engine; CV extraction itself is unchanged.

## Executable CV-field rules (2026-11-14)

All 28 picker choices map to persisted CandidateCVProfile facts. Free-text profile,
summary and objective share the parser's single summary source; they are not
fabricated as separate facts. Named paths and operators are validated, not code.
Text supports case/accent-insensitive equality, contains and prefix/suffix; date
comparisons use conservative intervals for partial dates. Education and language
thresholds use explicit recognized levels, otherwise Unknown. Repeated-record
conditions may scope AND/OR/NOT to one education, job, certification or language
record so conditions cannot accidentally join different records.

Requirements express failure conditions (UnFit); priorities add confirmed weights.
Missing/unrecognized values propagate Unknown and never mean failure. Active rules
for the current role code apply on read to all CVs in Evaluation and Applications,
without a provider call, new CV reading, persisted human-decision changes or AWS.
UnFit goes last, then descending priority, with original/manual ordering as a tie
breaker. Unknown evidence is displayed. Saving/toggling a rule affects the next
view; disabled rules do not apply. Historical role codes remain independently
scoped. No automatic rejection or deletion of candidates occurs.

## Return to Old Primary Screening (2026-11-14)

The PO authorizes only a separate Selection Criteria tab in the current PDL shell,
not the other Old tabs. In the official local launcher RFONE_SELECTION_ENGINE=old
selects the existing primary_screening_service for screening and priority ordering.
The conversational PDL rule implementation and its rows remain preserved but are
not used by operational lists/actions. AWS/shared defaults are unchanged.

Criteria reuse existing PrimaryScreeningCriterion rows, services, immutable
snapshots, human evaluations and hard-disqualifier semantics. New criteria are
scoped to the selected PDL role code; existing common criteria are identified as
shared. Owner-only create/edit/toggle, CSRF and version checks apply. The form
exposes Old's levels 0-4, coefficient/direction, blocking level, evidence/guidance,
signal mapping and missing-evidence question settings. No seed runs on GET.

The explicit Apply Selection Criteria action creates historical Old screening
runs for the current PDL candidates. Stored run IDs/signature preserve context;
GET never calls AI or rewrites historical results. Normal candidates precede
blocking cases, ordered by Old's internal priority index (never a probability or
a displayed score). Human decisions remain separate. The local ChatGPT transport
is passed explicitly to Old's generic evaluator, so no Bedrock/AWS is called.

## PDL defaults versus research-owned criteria (2026-11-14)

Approved correction: configuration owns a PDL's default criterion definitions.
Each new research Position copies every default criterion (including inactive
criteria and all nested dictionaries/lists) into independently owned native Old
criterion rows. Default updates never propagate to existing research; research
edits never update defaults or other research. The empty copy is also final: later
default additions cannot leak into an already-open empty research.

A nullable research_id on native PrimaryScreeningCriterion distinguishes default
rows (null) from research rows. Native default enumeration excludes research rows;
explicit research screening passes its owner ID and exact criterion IDs. Native
immutable evaluation snapshots and past screening runs remain untouched. A copied
criterion starts its own version history; source IDs/versions are kept in the
Position context. Scope checks, owner/manager grants, CSRF and concurrency checks
apply to both editors. Defaults are managed from Configuration; the existing
Selection Criteria tab edits only the selected research's copy. No new tab.

A guarded explicit local initializer adds the nullable column/index and freezes
the six pre-existing research definitions once, with backups. It never rewrites
criteria, CVs or historical runs. Official launcher verifies the additive schema
before starting. Role changes on a draft research create the new role's copy only
once and retain earlier role copies for audit. AWS is never contacted.
