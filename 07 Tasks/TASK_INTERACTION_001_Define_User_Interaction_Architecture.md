# TASK_INTERACTION_001 — Define RF-One User Interaction Architecture

**Type:** Documentation only. No software implementation.

---

## PURPOSE

Documentare l'architettura iniziale di interazione utente di RF-One.

Questa NON è una specifica grafica. NON definire layout, colori, menu, componenti UI o design system.

L'obiettivo è stabilire:

- quali dispositivi/interfacce servono a RF-One;
- quale tipo di lavoro viene svolto su ciascuno;
- il modello iniziale di autenticazione/autorizzazione;
- il ruolo del mobile;
- il ruolo dell'acquisizione di documenti/evidenze;
- il principio con cui ogni nuovo modulo operativo dovrà essere verificato rispetto a questa architettura.

DOCUMENTATION ONLY. Non implementare software.

## 1. Fundamental principle

RF-One non deve essere progettato come un'unica interfaccia identica su ogni dispositivo. Il tipo di interazione dipende dal dispositivo e dal contesto operativo.

Canonical initial model: Desktop/Laptop Web = full Operational Workspace; Mobile = contextual interaction surface. Il mobile NON è, per ora, una replica ridotta del software desktop.

## 2. Desktop-first web application

La prima interfaccia operativa completa di RF-One sarà una Web Application desktop-first, che supporta funzioni complesse (domain/module navigation, operational management, configuration, data review, reconciliation, analysis, complex workflows, personnel management, purchasing, payroll, financial/administrative workflows, reporting, system administration). Non definire ancora layout, sidebar vs top navigation, dashboard structure, cards, visual design, gerarchia di pagina dettagliata — decisioni successive basate sui moduli reali.

## 3. User identity and authentication

RF-One deve avere una propria User Identity. Separare Authentication (Who are you?) da Authorization (What are you allowed to see/do?). L'architettura deve poter supportare secure login, password-based authentication inizialmente se appropriato, meccanismi più forti (MFA/passkeys), session security, device/session management dove necessario. Non scegliere provider, framework o protocollo specifico. Non implementare nulla.

## 4. Authorization model

Autorizzazione iniziale semplice e comprensibile, concettualmente simile al modello Clover. Un Administrator determina, per ciascun User: quali Domains può vedere; quali Modules; quali Pages/Functions; quali Actions; su quale organizational scope.

Conceptual hierarchy: User → Domain → Module → Page/Function → Permission → Scope.

Permission semantics possibili: VIEW, EDIT/EXECUTE, APPROVE, ADMINISTER. Non creare una tassonomia eccessivamente complessa ora.

## 5. Visibility principle

A User sees only what the User is authorized to access. Non progettare RF-One in modo che Domains/Modules/Pages non autorizzati restino visibili ma disabilitati. Se il User non ha autorizzazione → normalmente non deve apparire nella sua interfaccia operativa. L'esperienza RF-One del User è quindi composta dinamicamente dalle capability autorizzate.

## 6. Authorization scope

L'autorizzazione deve supportare anche uno scope organizzativo (Organization/Company, Legal Entity, Restaurant Location, altre unità operative future). Esempio concettuale: User A → Restaurant/Purchasing → VIEW+EDIT → Location: Mount Dora; User B → Restaurant/Purchasing → VIEW → All Locations. Non hardcodare permessi specifici di Rome's Flavours nell'architettura generale.

## 7. Mobile role

Il mobile NON è considerato, per ora, l'ambiente primario per operare il sistema RF-One completo. Non riprodurre di default workflow desktop complessi su schermo piccolo. Casi d'uso mobile iniziali: alerts, notifications, suggestions, approvals, confirmations, quick decisions, quick actions, status checks, capture di Reality/evidenze/documenti. L'architettura mobile potrà espandersi se requisiti reali di modulo lo giustificano.

## 8. Mobile capture

Funzione chiave mobile: acquisizione di informazioni dalla Reality (fotografare una ricevuta, una fattura, un altro documento business, catturare immagine di equipment, evidenza di un problema operativo, potenzialmente altri media/dati in futuro).

Esempio: Mobile camera → capture receipt image → preserve original evidence → route to appropriate RF-One module → extraction/interpretation → Domain workflow.

Per Purchasing: Photo/document → Purchasing acquisition → Purchase Document → Purchase Lines → normal Purchasing workflow.

## 9. Capture is transversal

NON rendere la cattura mobile di foto/documenti concettualmente di proprietà di Purchasing. Il meccanismo di acquisizione è una capability di interazione transversale.

Concettualmente: Capture → Evidence/Source → Routing → Relevant Domain/Module. Purchasing è semplicemente un consumer.

Distinguere: Interaction capability (Document/Evidence Capture) da Domain processing (Restaurant/Purchasing, Personnel, Maintenance, Operations, ecc.). Non creare questi futuri Domains/moduli solo perché citati come esempi.

## 10. Source preservation

Il materiale catturato da mobile deve rispettare i principi RF-One di Reality/Evidence. La sorgente catturata originale deve essere preservabile come evidenza/provenienza. L'interpretazione derivata deve restare distinguibile dalla sorgente.

Concettualmente: Original Image/Document → Source Evidence; Extraction/Recognition → Interpretation/structured facts; Domain → consumes structured facts and evidence. Non definire ora l'implementazione di storage.

## 11. Routing

L'input catturato deve essere eventualmente instradabile al modulo appropriato, basato su scelta esplicita dell'utente, contesto, riconoscimento del documento, inferenza di sistema, workflow configurato. Non decidere ora l'algoritmo di routing. Il requisito architetturale è solo che Capture e Domain Processing restino separabili.

## 12. Mobile security

L'interazione mobile resta legata a User Identity e Authorization. Un User mobile deve poter solo: catturare per scope autorizzati; vedere alert autorizzati; eseguire approvazioni/azioni autorizzate; accedere ai dati permessi dallo stesso modello di autorizzazione usato dalla Web application. Non creare un modello di permessi mobile separato. Un'unica architettura di identità/autorizzazione deve governare tutte le superfici di interazione.

## 13. Hardware/software interaction principle

L'architettura software RF-One non deve assumere che ogni funzione appartenga a ogni superficie hardware/interfaccia. Le capability di interazione devono essere mappate all'hardware/contesto che meglio le supporta.

Initial model: Desktop/Laptop → complex cognition and operational control; Mobile → context, capture, alert, approval, quick interaction. Future hardware/interface surfaces possono essere aggiunte solo quando un modulo/caso d'uso reale lo richiede. Non speculare estensivamente su dispositivi futuri.

## 14. Module readiness review

Strong development principle: ogni volta che un Domain/Module diventa abbastanza maturo da muoversi verso l'implementazione operativa, RF-One deve eseguire una Interaction Architecture Review. Per quel modulo chiedere:

1. What does the User actually need to do?
2. Which actions require desktop Operational Workspace?
3. Which actions naturally belong on mobile?
4. Does the module require Capture?
5. Does it require alerts/notifications?
6. Does it require approval/confirmation actions?
7. What authorization granularity is required?
8. What organizational scope is required?
9. Does the existing interaction architecture support these functions?
10. If not, should the module adapt to the architecture OR should the interaction architecture itself evolve?

Importante: l'architettura di interazione attuale è una fondazione, NON un vincolo immutabile. La realtà dei moduli operativi può richiedere che l'architettura evolva.

## 15. Bidirectional coherence

Formalizzare il principio: Module requirements ↔ Interaction Architecture. Non forzare un requisito operativo valido in un'architettura di interfaccia inadatta solo perché l'architettura è stata documentata prima. Allo stesso modo, non permettere che ogni modulo inventi il proprio modello di interazione/sicurezza scollegato. Quindi: i moduli devono essere verificati per coerenza con l'architettura di interazione condivisa; l'architettura condivisa deve essere rivista quando requisiti legittimi di modulo espongono una capability mancante.

## 16. Product/Domain boundary

Non spostare la semantica di Domain nell'architettura UI. Esempio: Purchasing definisce Purchase Document, Purchase Line, Supplier Product, classification, ecc. L'Interaction Architecture definisce solo COME un User interagisce con quelle capability: desktop review, mobile capture, approval, notification, permissions. Il Domain resta autoritativo per il significato di business. Il layer di interazione resta autoritativo per l'interazione uomo-sistema.

## 17. Out of scope

Non definire ancora: layout UI esatto, navigation design, design system visivo, framework CSS/frontend, scelta React/Vue/Angular, native mobile app vs PWA, authentication provider, implementazione OAuth, schema database, endpoint API, notification provider, implementazione camera, implementazione OCR, cloud storage, infrastruttura di deployment. Sono decisioni implementative successive.

## 18. Document placement

Ispezionare l'architettura di repository esistente e collocare il documento canonico nella posizione più coerente dell'esistente architettura Software/Product. Preferire l'aggiornamento di un documento architetturale esistente se già pertinente, piuttosto che creare duplicazione inutile. Se non esiste un file canonico adatto, creare un documento chiaramente nominato come `03 Software/User Interaction Architecture.md` o il percorso strutturalmente più appropriato in base all'organizzazione attuale del repository. Aggiornare solo i riferimenti README/indice necessari. Non ristrutturare il repository.

## 19. Future module checklist

Includere nel documento canonico una checklist riutilizzabile:

MODULE INTERACTION READINESS

- Desktop functions identified
- Mobile functions identified
- Capture requirements identified
- Alert requirements identified
- Approval requirements identified
- Authorization requirements identified
- Scope requirements identified
- Evidence/provenance requirements identified
- Existing architecture sufficient? YES/NO
- Architecture change required? YES/NO

Questa checklist deve essere riutilizzabile ogni volta che un modulo si avvicina all'implementazione operativa.

## 20. Report

Create `07 Tasks/Reports/TASK_INTERACTION_001_REPORT.md` with sections: A. Summary; B. Canonical document placement; C. Desktop Web role; D. Mobile role; E. Authentication; F. Authorization; G. Visibility rule; H. Organizational scope; I. Mobile Capture; J. Transversal Capture capability; K. Evidence/provenance; L. Hardware/software interaction principle; M. Module Interaction Readiness Review; N. Bidirectional architecture evolution; O. Files created/modified; P. Remaining unresolved implementation choices; Q. Git scope confirmation.

## 21. Git

Do NOT run `git add`, `git commit`, or `git push`. At the end print only: task file created; canonical architecture document created/modified; report created; other files modified; any unresolved issues; confirmation that no git add/commit/push was performed.
