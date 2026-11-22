# Selection — Workflow operativo e passaggio a Training
**Data:** 2026-11-22  
**Stato:** consolidamento delle decisioni funzionali più recenti; non sostituisce il modello concettuale di Selection o la valutazione basata su evidenze del dominio.

## 1. Ambito
Selection è il dominio di valutazione e scelta, non un semplice parser CV. La sua interfaccia operativa deve mantenere separate **Job Position**, **Candidate**, evidenze e decisione di selezione.

## 2. Workflow approvato
- Pagina della posizione, pagina del candidato e stato della candidatura.
- Import CV e collegamento con Indeed quando previsto; nessuna dipendenza strutturale da Indeed.
- Intervista AI iniziale indicativamente 10–15 minuti: strumento di raccolta di evidenze, non autorizzazione a prendere autonomamente la decisione finale.
- Possibilità di confrontare candidati e registrare criteri, indicatori e motivazioni; dati non conosciuti restano tali.
- Stato `Draft` prima dell'attivazione, `Active` quando la posizione raccoglie candidature, `Closed` quando non accetta più candidature. Il comando di chiusura e gli effetti sui candidati devono essere espliciti; nessuna email di rifiuto deve partire per semplice cancellazione della posizione senza scelta autorizzata.

## 3. Handoff a Training e Registry
L'azione approvata dall'utente si chiama **Send to Training**.
- Selection crea o **riutilizza** una sola persona nel Registry canonico; non duplica il dipendente.
- Invio a Training e invito associati allo stesso profilo, non a una nuova anagrafica.
- Lo stato iniziale nell'anagrafica è `Trainee` quando applicabile, separato dal record payroll.
- L'invito Training deve essere idempotente e tracciato: una persona, una identità, anche con ingressi diretti in Training.

## 4. Decisioni da non inventare
La logica dei prefiltri, criteri di idoneità, intervista e autorizzazioni deve provenire dalle specifiche approvate del dominio; nessun punteggio AI non autorizzato. La chiusura della posizione con email ai non selezionati richiede una procedura e approvazione esplicita.

## 5. Verifiche
Test con candidati sintetici e casi di identità già esistente; verifica draft→active→closed, inviti duplicati, notifica del rifiuto, audit, permessi e multi-sede. Gli esiti di test locali non provano il deploy AWS.
