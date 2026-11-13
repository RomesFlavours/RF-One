# Development and publication language policy

**Standing instruction — UI_DEVELOPMENT_LANGUAGE_001, approved by the Product Owner on 2026-11-03.**

When the Product Owner develops or tests RF-One locally, the entire user interface must be in Italian. This includes navigation, forms, buttons, dialogs, validation and error messages, progress, generated client-side content, accessibility labels and How Works. Do not leave secondary pages such as Guided Reconciliation in English.

When the Product Owner explicitly asks to push/publish to Git or deploy to AWS, prepare and verify an English shared/release version BEFORE the push/deployment. The English release must include the same complete interface and How Works. That request authorizes the language preparation necessary for the requested release; this policy by itself does not authorize a push or deployment.

Preserve the Product Owner's Italian local working copy across release preparation and publication. Prefer explicit environment/locale selection with English as the shared/production default and Italian selected by the official local launcher. Otherwise prepare an isolated release checkout/artifact; never translate the working copy back to English and leave it that way after publication.

Do not translate stored financial facts, merchant/WHO names, imported descriptions, external account names, IDs, API fields, status codes or CSV schemas. Localize their human explanations and visible labels. Preserve original values and accounting logic.

Before a release verify both: local Italian still works; the shared/deployed interface defaults to English. Before and after local UI work verify the page plus dialogs and JavaScript-generated messages. Apply the existing How Works standard in both languages and describe only implemented behavior.
