# Pagina candidati su Aruba — istruzioni di pubblicazione (Hosting Windows)

Pagina dove il candidato inserisce nome, cognome ed email, riceve un codice di 5 cifre da
`rfone@romesflavours.com` e, dopo la conferma, entra direttamente nella propria candidatura su Selection (AWS).
Dettagli tecnici: [README.md](README.md).

## Ambiente

| Punto | Valore |
|---|---|
| Hosting | Aruba **Hosting Windows Basic**, Windows Server 2022 (IIS), **PHP 8.2.35**, FTP porta 21 (comunicato dal Product Owner, 25/10/2026) |
| Sito `romesflavours.com` / `www` | resta su **Wix**: questa pagina non lo tocca |
| Indirizzo della pagina | **`https://careers.romesflavours.com/index.php`** |
| Cartella FTP | **`/careers`**, nella radice FTP, accanto alla cartella Aruba `mdb-database` |
| Dati temporanei (sessioni, contatori, log) | `/mdb-database/rfone-careers`, creata dalla pagina: per Aruba è scrivibile e i suoi file **non possono essere scaricati dal web** |
| Certificato HTTPS | i piani Windows includono un certificato **Actalis Wildcard DV**, quindi `careers.romesflavours.com` è coperto se attivo sull'hosting |

## Perché Wix non è toccato
Wix serve `romesflavours.com` e `www.romesflavours.com`. La pagina usa un **nome diverso**, `careers.romesflavours.com`,
che punta all'hosting Aruba. **Non modificare** i record DNS `@` (radice), `www` e `MX`: cambiano solo quelli del
nuovo terzo livello `careers`.

## Passi

### 1. Terzo livello `careers` (pannello Aruba)
1. Area clienti Aruba → **Gestisci** su `romesflavours.com` → **Terzi livelli** → nome `careers`, servizio
   **Hosting Windows** (quello esistente). Se Aruba chiede la cartella di destinazione, scegli `careers`.
2. Verifica che `https://careers.romesflavours.com` sia coperto dal certificato SSL dell'hosting (pannello Hosting
   Windows → SSL). HTTPS è obbligatorio: senza, la pagina non parte.
3. Se Aruba crea il terzo livello in una **cartella diversa** da `/careers`, carica il pacchetto in quella cartella:
   la pagina funziona in qualsiasi cartella, e `check.php` (passo 4) conferma dove ha trovato `mdb-database`.

### 2. Prepara il pacchetto (sul PC)
Da una finestra di comando, nella cartella `aruba-careers`:

```text
"Prepara Pagina Candidati Aruba.cmd" verifica
```

Scrivi la password della casella `rfone@romesflavours.com` quando richiesta (non viene mostrata). Si apre
`%LOCALAPPDATA%\RF-One\Selection\aruba-careers-upload`, con dentro la cartella **`careers`** pronta, e viene
stampato l'indirizzo di `check.php`. La cartella contiene la password e il segreto condiviso, fuori da OneDrive e
da Git: **non inviarla a nessuno**.

### 3. Carica via FTP (porta 21; meglio FTPS, porta 990, se il client lo consente)
Trascina l'intera cartella **`careers`** nella **radice FTP**, accanto a `mdb-database`:

```text
/                         radice FTP dell'hosting Windows
├── mdb-database/         (di Aruba: non toccarla; la pagina vi crea rfone-careers)
└── careers/
    ├── web.config        protezioni IIS: private/ mai servita, niente elenco file
    ├── index.php
    ├── check.php
    ├── assets/careers.css
    ├── assets/careers.js
    └── private/
        ├── lib.php
        ├── config.php    password SMTP e segreto condiviso
        ├── config.sample.php
        └── blocked.html  file sonda per check.php
```

### 4. Verifica il piano reale
1. Apri l'indirizzo di `check.php` stampato al passo 2 (`https://careers.romesflavours.com/check.php?key=...`).
   Deve dire **"Everything the careers page needs is available."**: PHP 8.2, estensioni, **Folder private/ closed
   to the web**, **Data folder writable** (percorso con `mdb-database\rfone-careers`), sessioni e **SMTP login**.
2. Apri a mano `https://careers.romesflavours.com/private/config.php` e `.../private/blocked.html`: devono dare **404**.
3. Spegni la verifica: rifai il passo 2 **senza** `verifica` e ricarica soltanto `careers/private/config.php`.

Se una riga è rossa, o il sito dà **errore 500**, mandami lo screenshot. In caso di errore 500, prova anche a
rinominare temporaneamente `web.config`: ci dice se una sua sezione è bloccata dal piano. Correggo io.

### 5. Prova la pagina
Apri `https://careers.romesflavours.com/index.php?position=prova12345` → modulo First Name, Last Name, Email,
**Receive Code**. Con la tua email ricevi il codice e vedi **Welcome, ...!**. Il ritorno a Selection funziona
solo dopo il passo 6, ed è normale.

### 6. Modifiche su AWS — **solo con la tua autorizzazione** (le eseguo io)
1. `python make_upload.py aws-secret` → stesso segreto in Secrets Manager (`rfone-selection/candidate-identity-handoff`).
2. `rfone-selection`: variabile `RFONE_SELECTION_CANDIDATE_IDENTITY_URL=https://careers.romesflavours.com/index.php`
   e segreto `RFONE_SELECTION_IDENTITY_HANDOFF_SECRET` = ARN del punto 1 (il permesso di lettura è già nella policy versionata).
3. Snapshot RDS, migrazione additiva `c2b720261025`, deploy di `rfone-selection` dal ramo
   `feature/selection-aruba-identity`, che porta in produzione anche il workspace Selection in inglese, oggi assente.
4. Prova reale: posizione aperta → Verify your email → codice → candidatura → ritorno e ripresa.

Nessuna uscita Internet da AWS è necessaria: l'email parte da Aruba, AWS riceve solo il token.

### 7. Consegna in casella (consigliato)
Nel DNS manca un record SPF: senza, Gmail e Outlook possono mettere i codici nello spam. Aruba indica
`v=spf1 include:_spf.aruba.it -all`; se anche Wix o altri servizi inviano email come `@romesflavours.com`,
vanno inclusi. In caso di dubbio dimmelo e preparo il record.
