# Bank final WHO / WHY page logic

**Decision:** BANK_WHO_WHY_FINAL_LOGIC_001  
**Approved by the Product Owner:** 2026-11-05  
**Status:** Final approved functional direction; documentation does not certify implementation. Current working prototype: BANK-2026-11-04, port 5104.

## 1. WHO page: recognize WHO

One WHO page provides the different existing ways to recognize WHO: pattern discovery and review, extraction rules, explicit textual rules, name/alias recognition and AI/web investigation of unresolved descriptions. Reuse functioning engines and preserve user-authored rules and versions.

The user can define where the WHO occurs within a recurring pattern (between specified text boundaries), simulate extraction and inspect the results. Automatic pattern discovery is assistance, not an assumption that useful patterns have already been discovered.

WHO may be an explicitly approved conventional identity used by the Product Owner (for example PINO PERSONAL, COMPANY CAR or VARIOUS RESTAURANT). Such assignments are intentional and must not be replaced by a literal merchant name merely because an extractor finds one. Differing outputs require inspection; they are not automatically erroneous rules.

This page answers which WHO to assign. It does not determine WHY as part of recognizing that WHO.

## 2. WHY page: associate WHO with WHY

One WHY page provides:

1. Direct WHO-to-WHY associations where the result is unambiguous in its configured scope, including the applicable account/card context when relevant.
2. Rules where the WHO alone does not determine a unique WHY. Conditions and evidence select the applicable WHY; keep unresolved cases explicit rather than imposing one default.
3. At the end of the same page, the fixed WHY-to-WHAT mapping table.

Examples requiring contextual rules include AMAZON (purchase/order evidence and, when necessary, separate item allocations) and Zelle payments to employees (the recipient alone does not establish the purpose of each payment). Do not assume that every payment to an employee has the same purpose.

General, WHO-category and individual-WHO rules remain available within this WHY responsibility. Their overlap/conflict handling and simulation follow BANK_RULE_SCOPE_AND_WHO_CATEGORY_001; this decision does not impose an automatic specificity priority.

## 3. WHY determines WHAT

WHY-to-WHAT associations are fixed configured mappings. After WHY is selected, derive WHAT from that mapping; do not ask the user or AI to choose WHAT independently for each movement. A missing mapping is a configuration gap to resolve, not permission to invent WHAT. Where an operation requires multiple allocations, each allocation follows its selected WHY's mapping.

## 4. User flow and precedence

The logical sequence is WHO recognition, then direct or conditional WHO-to-WHY determination, then the fixed WHY-to-WHAT mapping. The WHO and WHY pages are the clear places to manage these two responsibilities, within the single reconciliation workflow.

Use Italian in local development, contextual How Works on each page and anchored help for modals. Rule editing remains understandable, with simulation before application and preservation of decisions already protected by the system.

This decision governs the final organization of WHO recognition and classification pages and supersedes incompatible earlier UI/flow proposals in that scope. It does not authorize deleting existing rules, changing financial data, replacing the current prototype, or publishing. Earlier engine designs and experiments are implementation history, not competing definitions of this final flow.

## 5. Navigation, Pannello and Ripartizioni (Product Owner, 2026-11-05 — BANK_LAYOUT_NAVIGATION_001)

Additional decisions of the same day, implemented in the BANK-2026-11-04 prototype (port 5104). They reorganise layout and navigation only: engines, rules, catalogs and data are unchanged.

**Tabs**, from the left: **Pannello · Carica e riconcilia · Riconcilio · Conti e carte · WHO · WHY · Configurazione**.

| Before | After |
|---|---|
| — | **Pannello**: new first tab and Bank Home (`/bank`). It does not replace Riconcilio. |
| Carica e riconcilia at `/bank` | Second tab, at `/bank/work` (functions unchanged). |
| Controlla movimenti | **Riconcilio** (same functions). |
| Regole WHO | **WHO** |
| Regole WHY | **WHY** |
| Ripartizioni (tab) | Section 3 of the WHY page; leaves the menu. `/bank/split` opens WHY › Ripartizioni; one movement's split stays at `/bank/split/<id>`, under the WHY tab. |
| Esportazione mensile (tab) | Bottom of Pannello; leaves the menu. The check and the download stay on `/bank/export`, under the Pannello tab. |

Pages leaving the menu keep their access item (ACCOUNT_ITEM_ACCESS_001) and their address.

**Pannello**, in this order: (1) general state of data and reconciliation; (2) pending items, shown only when present, each linking to the page that already performs the action — nothing is started from Pannello; (3) P/L area for a selected period, with print/PDF export — **not implemented** ("Da implementare": no figure is computed or shown, no accounting engine is introduced by the layout); (4) the existing monthly export. The period selection is for consulting and exporting only; uploading files never asks for a month.

**WHY page**, in four sections: (1) direct WHO → WHY associations unique in their context (read-only view of the WHO + Source classifications; edited in Configurazione › WHO); (2) rules for variable cases (WHO WHY rules, MULTIPLE mode, WHY to determine — e.g. AMAZON, Zelle payments to employees); (3) **Ripartizioni**: one movement distributed over several WHY, reusing the existing split function; (4) at the bottom, the fixed WHY → WHAT mappings (read-only; edited in Configurazione › WHY). No editor or service is duplicated.

**Section bookmarks (ovals)**: below the tabs, a page made of several sections shows its sections as ovals in the style of Carica e riconcilia. They are bookmarks within the same page: they open no other page, start nothing and change no data; filters and contents are kept. One component (`_bank_macros.html` `section_nav`), used on WHO, WHY and Pannello.

**WHO page**: tab "WHO"; window title "WHO"; page title **WHO Riconoscimento**. Sections: Pattern ed estrazione · Regole testuali · **WHO Status** (formerly "WHO Search Text"; opens by default on the movements with WHO not recognised, the filter still shows the other states and the count follows it) · Ricerca AI · WHO noti e regole. Explanatory paragraphs and technical eyebrows are moved to the contextual help.

**How Bank works**: the help link sits at the far right of the tab bar, separated from the tabs (the Selection placement): "Come funziona Bank" / "How Bank works" on Pannello, "Come funziona questa pagina" / "How this page works" elsewhere. It opens the page's section of the Bank guide in the standard help modal, keeping the page as it is; every modal has a "?" to its exact section.

The new general AI flow for reconciling the records still unresolved is postponed and will be designed last.

## 6. "Riconosci WHO" (Product Owner, 2026-11-05 — BANK_WHO_RECOGNISE_MODAL_001)

The modal opened by **By Text** in WHO Status (formerly "Text to search") lets the person associate the description of one movement with a **specific** WHO or a **generic** WHO — for an occasional purchase the person may prefer e.g. "Acquisti vari" to the shop name. Example approved: for CITY PHENOMENAL @MCO 456 the person may choose "Acquisti vari"; it is an allowed choice, not a rule applied automatically to every airport purchase. The existing function (the text as name or alias of a specific WHO) is kept.

Approved layout: title "Riconosci WHO" with "?" and ×; compact movement (original description, date and amount, Source and owner); then (1) Specifico / Generico; (2) "Chiedi un suggerimento all'AI"; (3) the WHO suggested or selected, marked as already present or new; (4) choose another WHO or create a new (generic) WHO; (5) "Testo da riconoscere nelle prossime transazioni", editable; (6) the state of the WHO → WHY association/rule applicable to the Source; (7) the contextual action to define the rule; (8) "Annulla" and "Salva associazione".

**AI behaviour** (ChatGPT/OpenAI, the Bank conversation provider, only on explicit request and only where Bank context sharing with ChatGPT is approved): it interprets the masked description and uses internet research when useful; for a generic WHO it looks first among the existing WHO and proposes a suitable one without creating a duplicate (a proposed name with the identity of an existing WHO resolves to it); otherwise it proposes a new name with a short reason. It saves and creates nothing before the person confirms. Unavailability or refusal is shown; the person can always choose by hand. This is assistance to defining a WHO and its rules, not the postponed general AI flow for unresolved records.

**WHO → WHY step**: for an existing WHO without an applicable association or rule, "Definisci regola WHO → WHY"; for a new WHO, "Crea WHO e definisci regola" — the click confirms the creation (WHO and its text) and opens the existing WHO WHY rule editor above the modal, with WHO, movement, Source and owner as context and a condition on the movement's Source. RF-One does not invent the WHY and does not extend the rule to other Sources; simulation, inactive save / activation and application are the existing ones; WHAT follows from the WHY's fixed mapping. One contextual path: closing the editor returns to the modal with its fields and the list position. If the person creates the WHO and cancels the rule, the WHO stays created and the modal says that its WHY is still to define; retrying does not create a duplicate.

**Saving** keeps three steps distinct: (a) the WHO and its reusable text/alias ("Salva associazione" or the creation above); (b) the WHO → WHY rule (editor); (c) its application to movements (simulation, activation, engine run). Saving the WHO is never a completed reconciliation, and protected human decisions stay protected. The former "WHO-WHY-WHAT association" window of the WHO page is replaced by (6)–(7); a WHO's possible WHY stay editable in Configurazione › WHO.
