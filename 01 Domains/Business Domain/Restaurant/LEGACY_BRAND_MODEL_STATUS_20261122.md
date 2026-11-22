# Legacy, Model e Brand — Registro di versione e autorità
**Data:** 2026-11-22  
**Stato:** puntatore di audit alle decisioni e al patrimonio; **non** una sostituzione del master Legacy approvato.

## 1. Legacy approvato
Il Product Owner ha approvato **Legacy 1.0 Rev.2** (6 novembre 2026) come riferimento di lavoro: premessa, 19 punti e Brand in conclusione. La trattazione mette al centro autenticità, patrimonio consolidato, valore e adattamento alle esigenze del cliente senza violare il modello. Il Brand chiude il documento, non sostituisce la premessa.

**Non ricostruire i 19 punti dalla memoria o dai riassunti.** Per il testo normativo deve essere identificato il file master approvato e verificata la corrispondenza integrale. In assenza di accesso al master, non dichiarare il documento canonico completo.

## 2. Custodia e cambiamenti
- Il master e il change log devono conservare versioni, autore, approvazione e motivo.
- Il lavoro su Legacy e Model determina la base funzionale: non va riscritto per giustificare codice già sviluppato.
- Le modifiche progettuali vengono discusse e approvate dal Product Owner; implementatori e verificatori non introducono nuove regole sostanziali.
- Distinguere **Legacy/Brand specifico di Rome's Flavours** dal concetto universale `00 Core/Brand.md`: non sovrascrivere la definizione Core del Brand con il materiale commerciale di un cliente.

## 3. Evidenza su Git
Il file `legacy-1.0-rev2.md` è presente come materiale di corso in più cartelle software dei branch di sviluppo. Le copie non sono automaticamente il master autorevole. È necessario individuare la versione finale approvata, verificarne il checksum e portarla nella posizione canonica prevista per Rome's Flavours, conservando provenienza e change log.

## 4. Punti aperti
Identificazione master firmato/approvato, confronto delle copie, struttura completa dei 19 punti, rapporti con Training e con il Brand di Rome's Flavours. Nessuna pubblicazione automatica del materiale integrale senza verifica.

## 5. Anomalia verificata nel testo Legacy di corso (blocco di attestazione)
Le due copie su `feature/clover-multisite-registry`:
- `03 Software/Server Course/content/courses/legacy-1.0-rev2.md`
- `03 Software/Management Course/content/courses/legacy-1.0-rev2.md`
sono **identiche per SHA Git** (`7dbe7da1b1e30fe96026e6dc6a63b756837892ab`). I titoli numerati passano da **15. Connection** a **17. People**, senza una sezione **16**. Sono quindi **18 punti numerati visibili**, più premessa e Brand; la richiesta approvata parla invece di **19 punti**. Inoltre il commento del file indica come fonte un invio del **24 settembre**, mentre la decisione di riferimento citata nel progetto è **Legacy 1.0 Rev.2 del 6 novembre**. Non assumere equivalenza fra queste due versioni. Occorre confrontare con il master approvato prima di promuovere il testo del corso a fonte canonica o colmare la sezione 16. Nessun testo mancante è stato inventato.
