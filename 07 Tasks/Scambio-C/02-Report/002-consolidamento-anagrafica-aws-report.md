# 002 - Preparazione consolidamento Anagrafica su AWS - Report

Comando: 002-consolidamento-anagrafica-aws.md
Attività: Anagrafica dipendenti - consolidamento per AWS
Chat di riferimento: Anagrafica, SW (01a18318-6031-7eb2-82ff-ac668723f065)
Data: 2026-11-04
Autore: C (Claude Code)
Esito: **PARZIALE**. Il lavoro è stato interrotto dall'utente («fermati») mentre giravano le suite di test complete.

## Attività svolte
1. Ho verificato lo stato reale in produzione (in sola lettura):

| Componente | Versione |
|---|---|
| Database (RDS) | e1b220261102 |
| rfone-web | interviews-consent-20261103t140633z, cioè commit 34a91a8, registrato in 1336e16 |
| Worker Clover | rfone-tips@62b68db5, uguale a fb49b8a |

   Ho confrontato i pacchetti live con i commit: web live = 1336e16 (differisce solo il registro dello schema) e worker live = fb49b8a.
2. Ho creato il branch isolato `integration/employee-directory-aws` (worktree `C:\Users\servi\rfone-wt\employee-directory-aws`) a partire da 1336e16. Ci ho copiato l'integrazione già fatta nel worktree `rfone-wt/interviews-employee-active`, che contiene il ciclo di vita del worktree edee, l'integrazione Interviews e l'applicabilità (approvata il 2026-11-03), e che mantiene i «record hold» oggi in produzione. Quel worktree non è stato toccato.
3. Ho ripristinato `interview_employee_options(db, location_ids=...)`, con il perimetro obbligatorio. Interviews passa `None` in modo esplicito, come da decisione PO del 2026-11-04. Ho aggiunto i relativi test.
4. How Works: ho portato su questa linea lo standard, il checker, il registro e la release checklist. Ho registrato le pagine dell'Anagrafica e di Interviews e riscritto la guida dell'Anagrafica con tutte le sezioni richieste. La guida precedente descriveva il perimetro Interviews eliminato dal PO.
5. Commit: a344112, 4257d90, 3c2a3eb, 272418a, 26a50d6 (hash del manifest calcolati sui byte LF). Nessun push.
6. Pacchetti LF costruiti con git archive: web sha256 d5673d67…, tips sha256 91176578…. Nessun file live è stato rimosso. Sull'artefatto estratto: catena delle migrazioni OK (testa e4a120261103, che contiene e1b220261102) e `CLOVER_RELEASE_VERIFIED` (16 test, nessuna scrittura).
7. Copia completa usa e getta: ho riusato il dump AWS in sola lettura delle 06:37, prodotto da un'altra sessione, senza nuovi accessi ad AWS. Ripristino su un mio cluster (porta 55461): 297 tabelle, 953.071 righe.
   - Audit pre-migrazione: 0 conflitti bloccanti, 64 persone, 1 account riusato, 35 da predisporre, 28 rinviati (senza timbrature), 36 persone con timbrature senza sede, nessun owner collegato a una persona.
   - Migrazione: 5,7 s; 293 tabelle invariate; righe preesistenti identiche; 35 shell INACTIVE senza permessi; 0 doppi account.
   - Controllo di avvio sul DB migrato: superato sia dal nuovo worker sia da quello live, quindi il rollback delle immagini è compatibile.
   - Esercizi sintetici sul clone, tutti OK: ripetizione idempotente; letture fallite, troncate o con timbrature fallite → nessuna cessazione; cessazione alla data dell'ultimo clock-in; sessione revocata; esclusione da Interviews; rientro senza riattivare l'accesso; cessazione per sede e finale; eccezione owner; account esterni invariati; tabelle operative invariate. Smoke test HTTP: tutte le pagine 200 e nessun dismesso offerto in Interviews.
   - Proiezione su dati reali: il primo ciclo dopo il rilascio non dismette nessuno, perché le 3 identità in attesa (link 65–67) sospendono le cessazioni; 28 persone diventano osservazioni tecniche. Dopo la conferma delle 3 identità: 39 posizioni chiuse, 13 persone dismesse (tutte con data) e 0 account attivi disattivati.

## Non completato
- Suite complete Data Store/Web/Training sul candidato e sulla baseline: interrotte. Il primo avvio non era valido per un errore del mio runner. Sono stati eseguiti solo i 106+ test centrali dell'Anagrafica (OK).
- Report tecnico in inglese in `07 Tasks/Reports/`, piano di deploy completo, cancellazione del cluster usa e getta. Il cluster è fermo ma i dati sono ancora in `%LOCALAPPDATA%\RF-One\Rehearsal-ED002` (contengono dati personali: vanno cancellati).

## Problemi e punti aperti
1. Il controllo How Works blocca il rilascio: le modifiche funzionali al piano Projects e alla home del trainer Training non hanno una Help (pagine legacy). Va scritta la Help, oppure serve una decisione.
2. La pagina Anagrafica è in italiano anche in produzione. Secondo UI_DEVELOPMENT_LANGUAGE_001 serve una versione inglese prima del deploy.
3. Sicurezza: l'RDS ha ancora due accessi pubblici diretti, 131.226.24.228/32 («temporary development access») e 104.145.102.85/32. Non li ho toccati.
4. Il processo dell'altra sessione (PID 27204, `with_temporary_rule.py`) sembra bloccato dalle 06:40, con il suo cluster attivo sulla porta 55447. La sua regola temporanea sul security group risulta già rimossa.
5. Il branch `feature/employee-directory-accounts` (EMPLOYEE_ACCOUNTS_001, migrazione f1a220261102) è un'implementazione parallela non rilasciata e non integrata.

## File modificati
- Branch `integration/employee-directory-aws` (commit sopra); worktree della baseline `C:\Users\servi\rfone-wt\baseline-1336e16`.
- Questo report.

---
## Testo integrale del comando 002

# 002 - Preparazione consolidamento Anagrafica su AWS

Data: 2026-11-04
Destinatario: C (Claude)
Attivita: Anagrafica dipendenti - consolidamento per AWS
Chat di riferimento: Anagrafica, SW (01a18318-6031-7eb2-82ff-ac668723f065)

Leggi prima il protocollo:
C:\Users\servi\OneDrive\AI-RF-ONE\RF One\07 Tasks\Scambio-C\README.md

Questo e il comando operativo 002. Il precedente file nel worktree era stato
salvato fuori dal canale di scambio; non costituisce un secondo incarico da eseguire.
Il contenuto operativo completo e riportato qui sotto: questo file e il riferimento
unico per l'esecuzione e il report del comando 002.

Report precedenti: 001-attivazione-scambio-report.md conferma l'attivazione del
canale. I report funzionali di Claude sull'Anagrafica e sulle decisioni approvate
sono stati forniti nella chat di riferimento il 03/11/2026: risultati dichiarati,
da verificare sulla versione finale integrata come richiesto sotto.

Percorso assoluto del report atteso:
C:\Users\servi\OneDrive\AI-RF-ONE\RF One\07 Tasks\Scambio-C\02-Report\002-consolidamento-anagrafica-aws-report.md

Usa esito COMPLETATO / PARZIALE / BLOCCATO e tutti i campi del protocollo.
L'eventuale report tecnico nel repository NON sostituisce questo report di scambio.

---

# Employee Directory — prepare AWS consolidation

Date: 2026-11-04. Assignee: Claude. Status: authorized preparation, no production deployment.

## Objective

Consolidate the completed local Employee Directory lifecycle implementation with
the current RF1 codebase and deliver a verified, reviewable release candidate.
The Product Owner has approved the functional decisions. Preserve them.

## Sources and integration

- Local changes: `C:\Users\servi\.codex\worktrees\edee\RF One`, branch
  `codex/employee-directory`; changes are currently uncommitted.
- Other active repository: `C:\Users\servi\OneDrive\AI-RF-ONE\RF One`.
- Inspect Git status, branches, local changes and actual deployed version before
  selecting the integration base. Use an isolated integration branch/worktree.
- Integrate relevant changes; do not copy the entire older checkout over the newer
  repository. Preserve other modules, runtime configuration and existing work.
- Check any Interview integration already implemented in the other chat. Do not
  replace it with a separate registry or duplicate lifecycle logic.

## Approved behavior to preserve

- RF1 canonical identity; explicit reconciliation of merchant + Clover employee ID,
  including multiple POS accounts belonging to one person. No name-based auto-merge.
- Disappearance ends only the affected site position. Dismiss the person when no
  active position remains. Cessation uses the last clock-in, even without clock-out.
- Clover identities without any clock-in/out remain technical observations, not
  registered employees/accounts. Do not fabricate a date for clock-out-only cases.
- Only successful complete source verification may cause cessation. Failed/partial
  reads, old file snapshots and unconfigured/unverified sites cannot do so.
- Native RF1 employees can exist without POS. Every registered employee has exactly
  one RF1 account. External accounts, such as Shelbi, need no employee record.
- Reuse confirmed account/Training/human identity bridges; never guess associations.
  Provisioned accounts are INACTIVE, with no usable credentials, invented email or
  grants. Replaced provisional accounts stay INACTIVE, unlinked and audited; they
  cannot be relinked as real accounts to another person.
- Dismissal blocks operational access and existing sessions. The owner retains
  administrative access, with OWNER_ACCESS_PROTECTED audit evidence, but the
  associated dismissed person remains excluded from operational/interview selectors.
- Workforce owns closure of organizational assignments. Directory must not close
  those records directly. Preserve all history. Rehire never silently restores access.
- Profile-driven permissions remain later work; no new automatic grants.
- Active employees grouped by site; Dismissis initially collapsed; account and site
  lifecycle visible; latest sync beside the action; current RF1 UI rules apply.
- No writes to Clover.

## Shared Interview contract

Preserve `interview_employee_options(db, location_ids=...)` and
`require_active_employee(db, employee_id, location_ids=...)` in the central service.
The former supplies only active canonical recipients; the latter revalidates at
submission and rejects dismissed/out-of-scope people, including stale page choices.
An empty site list means nobody; None means unrestricted scope and must not be used
as a fallback when authorization scope is missing. Historical interviews remain.
The page integration belongs to Codex in the chat "Prepare for an interview".

## Migration chain

Local revision `e3f120261103` currently follows `d9e220261029`. The latest handoff
reports production revision `e1b220261102`; verify the actual runtime and migration
DAG before changing ancestry. Integrate into the current chain without accidental
branches, missing revisions or incompatible edits to applied migrations.
Align models, worker startup guard and release manifest. Preserve IDs and references.

## How Works

Reuse the current How Works registry and conventions, absent from the older
checkout. Add Employee Directory help covering active/site/dismissed state,
reconciliation, technical observations, accounts and provisional replacements,
synchronization, suspended cessations, owner exception and retained history.

## Read-only AWS audit

Audit the actual application database using the employee_directory_audit tool,
adapted to the current schema if required. Report direct/indirect person-account
conflicts, missing/deferred accounts, no-clock identities, unscoped clocks and owner
associations. Do not guess or automatically repair ambiguous associations.
Never expose credentials or unnecessary personal data in reports.

## Complete disposable PostgreSQL rehearsal

Create a complete isolated disposable copy of real data and run the migration
there. Verify stable IDs, references/history, account uniqueness, no privilege
expansion, legacy no-clock handling, per-site/final cessation, session revocation,
owner exception, external accounts and Interview filtering. Exercise repeated,
failed and incomplete imports with synthetic changes only inside the copy.
Ensure operational data, sequences and services are unchanged. Verify the exact
identity of the disposable copy before removing it after the rehearsal.

## Verification and packaging

Run appropriate checks on the final integrated implementation, distinguishing
baseline defects from regressions. Earlier Claude reports list 86 unit tests,
13 Directory HTTP tests, and successful acquisition/poller/Bank/Projects/Training
checks; these are prior results, not substitutes for final integrated verification.
Baseline issues reported separately: two Training-under-Tips failures and Projects
service check 43 expecting an obsolete migration revision.

Build with LF text files, regenerate integrity hashes, verify the actual packaged
bytes and run the worker startup check against that artifact. Do not merely verify
the source tree. Preserve newer deployed functionality and service configuration.

## Deliverables and authorization boundary

Prepare coherent commits and an English repository report under `07 Tasks/Reports/`.
Report to the Product Owner in Italian using the repository REPORT format. Include:

1. Integration branch and exact commits; conflicts and resolutions.
2. Verified AWS runtime/schema version and resulting migration chain.
3. Read-only audit findings and complete PostgreSQL rehearsal evidence.
4. Final tests, artifact hashes and startup verification.
5. Remaining blockers, if any, and explicit release-readiness conclusion.
6. Concrete deployment, backup and recovery plan, including affected services and
   workers and any schema compatibility limitations of rollback images.

Authorized now: local integration/preparation, read-only AWS inspection and the
isolated disposable rehearsal. NOT authorized: production deployment, migrations
or personnel changes in the operational database, starting new production source
synchronizations, or Clover writes. Deliver the concrete release candidate for
the Product Owner's final deployment approval.
