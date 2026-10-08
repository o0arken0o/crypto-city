# Crypto City

Crypto City è un progetto completo con una città 3D e un avvio diretto per Windows.
Esplora i 12 edifici e apri le sale per vedere stato, attività, strategie, grafici e rischio dai dati del progetto.

## Avvio su Windows

1. Scarica questa repository con **Code → Download ZIP**.
2. In Esplora file scegli **Estrai tutto** e apri la cartella estratta.
3. Fai doppio clic su **APRI_CRYPTO_CITY.cmd** nella cartella che contiene anche `dashboard`, `engine` e `state`.
4. Attendi l'apertura del browser. Lascia aperta la finestra del server.

Serve Python **3.10 o successivo**, consigliato 3.12. La plancia usa la libreria standard di Python;
Three.js e OrbitControls sono già inclusi. Non servono Node, Git o una precedente installazione.
Se Python manca, il file di avvio mostra le istruzioni. Usa Chrome o Edge con JavaScript attivo.
Se il computer non supporta WebGL, puoi comunque aprire le 12 sale dalla lista degli edifici.

Il programma avvia il server di **questa cartella**, usando la sua cartella `state`.
La porta iniziale è 8977; se è occupata viene scelta una delle successive e l'indirizzo viene stampato nella finestra.
Si apre direttamente `/plancia#city`. Gli altri server restano attivi e le altre installazioni non vengono aggiornate.
Per chiudere il server usa **Ctrl+C** nella sua finestra.

## Le 12 sale

BTC Trader · ETH Trader · SOL Trader · XRP Trader · ADA Trader · CRO Trader · Market Scanner ·
Quant Analyst · Risk Manager · Portfolio Manager · Yield Agent · Chief Trading Agent.

Le sale leggono le API del motore. Valori mancanti o servizi non raggiungibili vengono indicati chiaramente;
non vengono sostituiti con guadagni o attività inventati. I sei trader sono viste delle strategie per asset.

## Interfaccia di Crypto City

Il menu contiene **Città, Strategie, Conferme, Agenti, Portafoglio, Mercati e Impostazioni**.
Le vecchie voci Sala trading, Sala rendite, Casa e i collegamenti social sono stati rimossi dall'interfaccia.
La configurazione dei provider AI necessari agli agenti è disponibile nelle **Impostazioni**.
Nome, icona e collegamenti dell'app installabile sono quelli di Crypto City.

Per aggiornare una copia già avviata senza sostituirne i dati, scarica
[Crypto-City-INTERFACCIA.zip](downloads/Crypto-City-INTERFACCIA.zip), scegli **Estrai tutto**
e copia la sua cartella `dashboard` dentro la cartella del tuo progetto, accettando la
sostituzione dei file. Poi premi **Ctrl+F5** nella città aperta nel browser.
La ZIP contiene solo nove file dell'interfaccia; non contiene motore, server o stato.

## Dati e sicurezza

La repository contiene lo stato, le ricerche e le strategie già presenti nella versione di Crypto Machine da cui deriva.
Lo storico eventualmente più recente sul tuo PC resta nella vecchia installazione: questo avvio non lo importa né lo sovrascrive.
Il server può aggiornare il proprio stato durante il normale funzionamento.

L'avvio locale usa solo `127.0.0.1`, tiene disattivato l'avvio automatico dei cicli e usa la modalità locale.
Per un collegamento a GitHub o un servizio online segui la [documentazione completa](docs/CRYPTO_MACHINE_ORIGINAL.md).
Token e impostazioni GitHub della vecchia repository devono essere riconfigurati per questa repository.
I workflow originali sono inclusi senza modifiche. Nella nuova repository tieni inizialmente **GitHub Actions disabilitato**;
abilitalo dopo aver configurato e scelto quali cicli eseguire. I cicli paper e rendite possono aggiornare lo stato anche senza chiavi AI.

Restano obbligatori backtest, paper trading, controllo del rischio, capitale massimo e approvazione del proprietario.
Gli agenti producono analisi e segnali: **gli ordini reali su Crypto.com richiedono la conferma esplicita del proprietario**.
Il motore non conserva chiavi di trading e non invia ordini automatici. Vedi [POLICY.md](POLICY.md).

Non è un consiglio finanziario. Risultati passati o simulati non garantiscono quelli futuri.

## Sviluppo e verifiche

```bash
python3 -m venv .venv
# Linux/macOS; su Windows: .venv\Scripts\python.exe
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover tests -v
python3 start_city.py --no-browser
```

PyNaCl serve alla gestione dei secret GitHub. Pillow è facoltativo per la generazione di immagini.
Le regressioni nel browser si eseguono separatamente con Playwright e Chromium:

```bash
python3 -m pip install playwright
python3 tests/browser_city.py
```

La mappa dei componenti riusati e delle route è in [CRYPTO_CITY_ARCHITECTURE.md](docs/CRYPTO_CITY_ARCHITECTURE.md).
La provenienza e gli hash della versione di partenza sono in [CRYPTO_CITY_SOURCE_SNAPSHOT.json](docs/CRYPTO_CITY_SOURCE_SNAPSHOT.json).
La mappa documenta anche i file dell'interfaccia aggiornati rispetto a quella versione.
