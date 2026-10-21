Cross-Domain Procedures e MyRF - prototipo locale

Avvio: eseguire Avvia.cmd. Aprire http://127.0.0.1:8765
Richiede Python 3, senza pacchetti aggiuntivi. Se il runtime Codex viene
spostato, eseguire python server.py da questa cartella.
Dati persistenti: demo.sqlite3 nella stessa cartella, transazioni SQLite.
Il server ascolta solo sul computer locale. Nessun servizio esterno.

Prova: Dipendente registra 22 rotti; FOH conferma 62; Mount Dora accetta
e spedisce; FOH riceve; Controllo di gestione registra la verifica.
Risultato: Winter Park 120, Mount Dora 338, riserva e transito zero,
intercompany 62 x $4 = $248, pratica chiusa.

La sezione 8 della 0.3 richiede il controllo per la chiusura del riassortimento.
T12 precedente richiede solo conferme e intercompany. Prevale 0.3:
il controllo e un ruolo di prova aggiuntivo, non un'assegnazione personale.
Non sono inventati nomi, coperture o autorizzazioni organizzative.

Limiti: selettore ruoli dimostrativo senza autenticazione; un articolo,
una direzione, trasferimenti completi senza differenze di ricezione.
Acquisti, inventari periodici, notifiche e altri scenari non implementati.
La scadenza 24 ore blocca l'accettazione tardiva; acquisto alternativo
e ricalcolo dell'eccezione non implementati. Massimo MD non specificato.
Intercompany solo registro locale, senza contabilizzazione o settlement.
La definizione 0.3 e distinta dalle pratiche ma non editabile in questa demo.
Ripristino esplicito disponibile a fondo pagina e cancella i dati demo.

Verifica automatica: python -m unittest -v test_flow.py
