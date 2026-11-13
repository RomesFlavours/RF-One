# Scambio comandi e report tra Codex e C

Percorso unico: C:\Users\servi\OneDrive\AI-RF-ONE\RF One\07 Tasks\Scambio-C
Non usare le cartelle 07 Tasks delle copie o dei worktree.

## Procedura
1. Codex scrive i comandi in 01-Comandi con nome NNN-nome-attivita.md.
2. L'utente dice a C: "comado" (parola di attivazione; vale anche "Hai un comando nuovo").
3. C legge questo protocollo, confronta comandi e report e prende il comando con numero piu basso ancora privo di report. Non ripete mai comandi gia rendicontati.
4. C legge interamente il comando e cancella subito il relativo file da 01-Comandi, prima di qualsiasi altra azione, conservandone il contenuto nel proprio contesto.
5. C esegue solo quanto richiesto e salva il report in 02-Report con nome NNN-nome-attivita-report.md. Poiche il file del comando non esiste piu, il report riporta in fondo il testo integrale del comando eseguito.
6. L'utente dice a Codex: "Hai un report nuovo" nella chat relativa all'attivita, che conserva il contesto del lavoro.
7. Codex legge il report associato all'attivita della chat corrente, verifica quanto necessario e scrive eventuali istruzioni in un nuovo comando numerato. Non prende automaticamente il report piu recente di altre attivita. Se il riferimento e ambiguo, chiede il numero del comando.

## Contenuto dei comandi
Numero, data, attivita e chat di riferimento (titolo o identificativo disponibile), obiettivo, contesto, percorsi di lavoro, istruzioni, limiti, verifiche richieste e percorso assoluto del report atteso. Citare eventuali report precedenti. La numerazione resta unica per tutta la cartella Scambio-C.

## Contenuto dei report
Numero del comando, attivita e chat di riferimento riportate nel comando, data, esito (COMPLETATO / PARZIALE / BLOCCATO), attivita svolte, file modificati con percorsi, verifiche e risultati, problemi, dubbi e punti aperti. Non dichiarare verifiche non eseguite.
Se serve un chiarimento, scriverlo nel report e fermare le sole attivita dipendenti dalla risposta.

## Conservazione
Non sovrascrivere o cancellare report. I file dei comandi vengono cancellati solo da C, solo nel momento previsto al punto 4 della procedura (regola dell'utente, 2026-11-04); il loro testo resta conservato nel report. I comandi gia rendicontati ancora presenti in 01-Comandi non vengono ne eseguiti ne cancellati. Per integrazioni usare un nuovo comando e relativo report. I comandi sono scritti da Codex; i report da C. La creazione di un comando non autorizza operazioni esterne al suo ambito.

