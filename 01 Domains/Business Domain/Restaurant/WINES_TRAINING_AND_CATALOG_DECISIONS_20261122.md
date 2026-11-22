# Wines — Catalogo e contenuti di formazione alla vendita
**Data:** 2026-11-22  
**Stato:** decisioni funzionali recenti, non prova del deploy o dell'esistenza del campo nel database operativo.

## 1. Catalogo vini
L'anagrafica del vino richiede **Vintage / Annata**, visibile nella pagina di amministrazione e persistito sul modello dati. La modifica a interfaccia e database deve essere verificata con import, modifica e lettura, senza perdere le altre proprietà della bottiglia.

## 2. Due livelli di conoscenza distinti
- **Tipo/stile di vino**: caratteristiche di base trasferibili fra etichette (uve/grape, territorio, stile, sensazione e profilo del cliente), con curiosità pertinenti. Esempio concettuale: distinguere Barolo e Nebbiolo pur partendo dalla stessa uva, senza inventare attributi non verificati.
- **Bottiglia presente in lista**: elementi che distinguono l'etichetta dal tipo/stile, inclusi produttore, annata, storia locale/tecnica e motivi concreti per proporla.

## 3. Formazione commerciale
- Tre livelli progressivi: **basico, intermedio, avanzato**; ognuno deve dare strumenti realmente spendibili con il cliente, non nozioni fini a se stesse.
- Il percorso vini è intrecciato con **il corso vendita dei Server**: il baricentro è riconoscere bisogni, emozioni e preferenze, non fare un esame da sommelier.
- Il prezzo e il margine riflettono la strategia di scoperta e valore; la quantità di 5 oz per bicchiere è una scelta commerciale, non una norma didattica universale.
- I contenuti specifici di bottiglia e tipo vino vanno verificati prima di essere pubblicati e aggiornati in maniera indipendente.

## 4. Confini
Wines gestisce catalogo e conoscenza prodotto; Training gestisce il percorso e le evidenze di apprendimento; Sales/Visual Menu presenta contenuti al cliente. Nessun automatismo di certificazione o prezzo deriva da questa specifica.

## 5. Da verificare
Schema attuale e versionamento annata, contenuti autorizzati, pubblicazione AWS e collegamenti con Visual Menu e Training.
