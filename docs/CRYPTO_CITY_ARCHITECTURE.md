# Crypto City: mappa e confini

Analisi del checkout `10d489651f96efcfda8812fbc29813b7ddf729dc`, prima dell'implementazione.

Il repository comprende motore deterministico, runner AI, script di ricerca e prove, plugin/agenti,
stato e strategie, sito pubblico, plancia, sale 3D, test e workflow GitHub. Crypto City cambia la
presentazione della plancia, non introduce agenti backend né nuove capacità di trading.

## Percorso dei dati

`workflow → scripts/engine → state e products → dashboard/server.py → API GET → Crypto City`

`approvazione proprietario → comandi esistenti → scripts/actions.py → segnale live`

Il checkout non contiene un client ordini Crypto.com: usa dati pubblici Coinbase/Kraken e segnali
che il proprietario esegue manualmente. Nessuna nuova chiamata a exchange, nessun ordine automatico.
L'interfaccia della città non decide approvazioni e non scrive stato.

## File e route

| Percorso | Decisione |
| --- | --- |
| `dashboard/index.html` | Nuova vista iniziale città, codice/CSS inline per rispettare le route statiche attuali; conservare DOM, comandi e hash operativi |
| `dashboard/charts.js` | Conservare il modulo delle sale precedenti; la home incorpora gli stessi helper in `city-charts` per funzionare anche senza questo file o la relativa route |
| `dashboard/vendor/three/` | Riusare Three.js e OrbitControls locali senza modificarli |
| `dashboard/office.html`, `sales.html`, `sims.html`, `ai.html` | Conservare sale e route |
| `dashboard/exchange.js`, `scene3d.js` | Conservare le scene esistenti; città isolata |
| `dashboard/server.py` | NON toccare: API, autenticazione, comandi, route, autostart, sito pubblico |
| `engine/`, `scripts/`, `agents/`, `commands/`, `hooks/`, `.claude-plugin/` | NON toccare: motore, integrazioni, audit/guardia e agenti |
| `state/`, `products/`, `POLICY.md` | NON toccare: dati, strategie, backtest, paper/live, limiti reali |
| `.github/workflows/`, `railway.json`, `requirements.txt` | NON toccare |
| `docs/`, nuovi test frontend | Documentare e verificare |

`/plancia` resta la home privata e diventa Crypto City. `/` resta il sito pubblico con il suo
redirect proprietario. `/index.html` e `/plancia/` conservano i redirect. Restano disponibili
`#oggi`, `#prodotti`, `#dafare`, `#team`, `#soldi`, `#mercati`, `#impostazioni` e gli alias storici.
`#city` e `#city/<id>` aggiungono home e collegamenti alle dodici sale. Nessuna modifica alle API.
Il server ammette solo i moduli applicativi esistenti: i nuovi script della città sono inline,
con import dinamici protetti delle librerie già servite.

### Compatibilità con le copie Windows precedenti

Le copie anteriori al commit `15c3169` non contengono `dashboard/charts.js` né la
route `/charts.js`. La home incorpora gli helper esistenti `drawRealCandles`,
`sparkline` e `fmtPrice` nell'oggetto `CryptoCityCharts`; sia le sale City sia il
terminale Oggi li usano senza importare moduli aggiuntivi dal server. Il backend
locale e le sue route restano intatti. Se la versione precedente non espone
`/api/candles`, viene mostrato "Prezzi pubblici non disponibili".

Il pacchetto Windows verifica comunque server, struttura del progetto e librerie
Three.js già presenti prima di sostituire la pagina. Il percorso del progetto può
essere scelto con una finestra di selezione; dopo un'installazione riuscita viene
ricordato in un file locale nella cartella del pacchetto per riutilizzarlo all'avvio.

`Crypto-City-START.zip` contiene un unico comando `APRI_CRYPTO_CITY.cmd` che installa
e apre la città. Cerca cartelle `crypto-machine*` sul Desktop e riconosce i checkout
interni alle cartelle estratte. La ricerca in ciascuna cartella è limitata a due livelli
e cento sottocartelle; anche l'elenco del Desktop ha un limite di cento cartelle.
Usa automaticamente solo un risultato compatibile; più copie richiedono una scelta.
Anche la selezione della cartella esterna viene risolta al checkout interno quando
è unico. Lo ZIP contiene i file alla radice, senza un'ulteriore cartella del pacchetto.

## Dodici edifici e fonti reali

| Sala | Fonte |
| --- | --- |
| BTC, ETH, SOL, XRP, ADA, CRO Trader | Viste mercato, non nuovi agenti; strategie associate per moneta esplicita nel titolo/regole o nel mercato collegato; fonti market-scanner, quant-analyst, quant-dev |
| Market Scanner | `market-scanner` |
| Quant Analyst | `quant-analyst` |
| Risk Manager | `risk-manager` |
| Portfolio Manager | `portfolio-analyst`, team rendite |
| Yield Agent | `yield-lead`, `yield-scout`, team rendite |
| Chief Trading Agent | `ceo` |

`GET /api/state`: stato, agenti, ultimo run, strategie, rischi, ledger, log, approvazioni.
`GET /api/live?team=trading|rendite`: attività corrente e risultati backtest/paper testuali,
segnali, report, rendimenti. `GET /api/candles`: grafici reali per tutte le sei monete.

I risultati di simulazione restano distinti dal P&L monetario registrato. P&L di una sala solo
quando il ledger contiene voci esplicitamente legate alle sue strategie; mai copiare KPI globali
come profitto di un agente. Dati assenti e fonti non raggiungibili sono indicati esplicitamente.
I trader non ereditano un ultimo run o uno stato operativo fittizio dai ricercatori comuni.

Il prossimo ciclo è un orario **programmato**, non una promessa di esecuzione: trading
22/00/02/04:17 UTC, rendite 23:47 UTC, pulse ogni ora :23. Visualizzazione Europe/Rome;
pausa del sistema evidenziata. Nessuna richiesta di avvio ciclo dalla navigazione della città.

## Fasi e verifiche

1. Mappa e baseline della suite esistente.
2. Home città, fallback HTML, modello dati e sale; controlli sintassi e dati.
3. Scena 3D isolata, touch/tastiera, gestione errori/moduli/WebGL e API.
4. Test browser desktop/mobile, navigazione di tutte le sale, route, dati assenti,
   autenticazione e regressioni JavaScript; suite Python completa.

La directory HTML resta visibile prima del caricamento degli script. Con JavaScript attivo le
sale restano apribili anche senza WebGL o rete; senza JavaScript vengono offerti i collegamenti
alle sale precedenti. La città non dipende da asset o CDN esterni. Gli ordini reali e i limiti
restano fuori dalla scena.

## Eseguire le regressioni

La suite standard comprende `tests/test_city.py`: ventuno controlli di markup, sintassi di tutte
le pagine e dei moduli JavaScript, associazione dati, P&L, assenza di mutazioni, orari e grafici
inline senza dipendenza da `/charts.js`. `tests/test_city_package.py` verifica l'installazione
su un checkout privo del modulo, il backup, l'idempotenza, il riuso del percorso e l'arresto
senza modifiche quando il checkout è incompatibile. Il pacchetto START aggiunge
regressioni per cartella esterna, ricerca automatica Desktop e copie multiple.
Python e Node sono necessari per eseguire anche i controlli JavaScript.

```bash
cd /workspace/crypto-machine
NO_PROXY=127.0.0.1,localhost,::1 no_proxy=127.0.0.1,localhost,::1 python3 -m unittest discover tests -v
python3 tests/browser_city.py
```

Il secondo comando richiede Playwright per Python e Chromium (`CITY_TEST_CHROMIUM` può indicare
l'eseguibile). Usa un server locale, un token temporaneo e una copia temporanea dello stato;
non scrive dati nel checkout e non invia comandi. Le richieste prezzi/live sono intercettate
con fixture deterministiche dichiarate nel test, mentre `/api/state` e le route HTML usano
il server reale. La mancanza di browser/Playwright produce skip espliciti, non una validazione.
Questi strumenti sono dipendenze di sviluppo, non aggiunte alle dipendenze del backend.
I workflow GitHub sono invariati.

Verifica della prima versione della città: 160 test della suite standard eseguiti, 158 superati e 2 test
immagini opzionali saltati per assenza di Pillow. Tutti i 14 scenari Playwright superati: WebGL
reale, raycast, dodici sale, mobile, aree touch, route/hash e browser back, errori API/moduli,
autenticazione, XSS e perdita del contesto WebGL. Nessun errore JavaScript non gestito e nessuna
richiesta di scrittura durante la navigazione della città.

Il pacchetto v2 è stato verificato anche sulle versioni storiche `641f309` e `d3f1e09`:
server e API stato/attività reali, dodici sale, otto sezioni, sette route HTML, terminale
e mobile. Nessun errore JavaScript, scrittura dal browser o richiesta `/charts.js`; tutti
i 136 file protetti di ciascun checkout sono rimasti invariati. I feed esterni erano
intenzionalmente bloccati: l'assenza di `/api/candles` o dei prezzi mostra il fallback previsto.
Il selettore cartelle Windows è verificato con simulazioni Tk; l'esecuzione nativa dei file
CMD resta da verificare sul computer Windows dell'utente.

Il comando unico del pacchetto START è stato verificato su un checkout temporaneo
`d3f1e09`, passando la cartella esterna: installazione, backup, server reale, API
stato, collegamento browser e secondo avvio senza duplicare processi o backup.
I file protetti sono rimasti identici; stato runtime isolato e generazione bytecode
disabilitata soltanto nel test. L'HTML resta quello verificato nei 14 test browser.

Il controllo preventivo della porta usa un bind locale senza connessioni TCP:
su Windows una connessione a porta ancora chiusa può andare in timeout anziché
rispondere immediatamente. I nuovi test verificano porta libera anche con connect
in timeout, riconoscimento di un listener senza contattarlo e arresto su errore di
permessi prima di avviare processi. `Crypto-City-START-FIX.zip` contiene questo
controllo; anche i link ai pacchetti precedenti sono stati aggiornati. Una porta
riservata o non utilizzabile conserva l'errore esplicito e non avvia un server.

Il server locale è stato verificato anche senza fixture per stato, attività di entrambi i team
e risultati registrati. I prezzi pubblici non sono stati verificati con dati live nell'ambiente:
il proxy ha negato la connessione Coinbase (CONNECT 403) e l'API candele ha restituito correttamente
"dati non disponibili". Sono stati aggiunti in una bozza dell'ambiente `api.exchange.coinbase.com`
e `api.coinbase.com`, preservando i preset esistenti. Il salvataggio della bozza non applica o
pubblica le modifiche: i feed vanno riverificati dopo l'attivazione delle impostazioni.

## Repository completa Crypto City

La copia autonoma parte dal commit `900fb5803508cc79b4ec1f768bc04adf62ccea78` di
`o0arken0o/crypto-machine`, con una nuova storia Git. Sono stati esportati soltanto
i file tracciati: backend, integrazioni, engine, agenti, policy, strategie, stato,
audit, workflow e la città restano gli stessi. Gli hash dei 122 componenti riusati
sono conservati in `CRYPTO_CITY_SOURCE_SNAPSHOT.json`. I dati della vecchia copia
Windows non vengono importati automaticamente né modificati.

I nuovi file `APRI_CRYPTO_CITY.cmd` e `start_city.py` avviano il server adiacente:
non sono installatori di aggiornamenti. La cartella di lavoro e `MM_STATE_DIR`
appartengono alla nuova copia; `MM_HOST=127.0.0.1` e `MM_AUTOSTART=false`.
I riferimenti GitHub e al sito della configurazione ereditata vengono rimossi
dall'ambiente del processo locale, mantenendo l'eventuale `MM_TOKEN`.

L'avvio cerca una porta libera fra 8977 e 8996 con il controllo bind già verificato.
I listener occupati vengono saltati senza contattarli o riusarli: lo stesso HTML
può appartenere a copie con stati differenti. `--port` permette un valore esplicito;
`--no-browser` serve alla verifica locale. Prima di aprire `/plancia#city`, il
launcher verifica `/healthz`, l'HTML esatto con le 12 sale e `/api/state` oppure la
richiesta di autenticazione. I normali salvataggi dello stato restano quelli del backend.

README e LEGGIMI descrivono l'avvio completo; il README precedente è conservato
in `CRYPTO_MACHINE_ORIGINAL.md`. I vecchi pacchetti di aggiornamento restano in
`downloads/` per conservare le relative regressioni e la provenienza, ma l'avvio
della nuova repository usa esclusivamente il comando nella sua radice.

I workflow sono byte per byte quelli originali. I cicli pianificati vanno tenuti
inizialmente disattivati nelle impostazioni della nuova repository: anche senza
secret AI possono aggiornare lo stato del paper trading e delle ricerche. Pages
richiede già `PAGES_ENABLED=true`; nessuna nuova pubblicazione Pages è configurata.

Verifica della copia completa: 178 test unitari eseguiti, 176 superati e 2 saltati
per Pillow opzionale; tutti i 14 scenari browser superati, incluse le regressioni
JavaScript, desktop/mobile, route precedenti e fallback WebGL. I 18 test del nuovo
launcher includono un avvio reale in una cartella temporanea con spazi e una
sentinella nello stato, provando che la copia serve i propri dati. Il setup cloud
con venv dedicato è stato installato e ripetuto; startup, pagina esatta, API stato,
route precedenti e Three.js sono stati verificati con stato runtime esterno.
Alla creazione della copia completa, i 122 hash della provenienza erano identici e il checkout originale era pulito.
L'esecuzione nativa del nuovo comando Windows resta da verificare sul PC.

## Pulizia dell'interfaccia di Crypto City

L'interfaccia e l'app installabile ora usano il nome **Crypto City** e un'icona con
la città e le iniziali CC. Il menu principale contiene Città, Strategie, Conferme,
Agenti, Portafoglio, Mercati e Impostazioni; la navigazione mobile offre le stesse
sezioni. Le dodici sale restano la vista iniziale.

Sono stati rimossi dall'interfaccia i collegamenti Sala trading, Sala rendite e
Casa, il ciclo social, LinkedIn e i pannelli promozionali del progetto precedente.
Gli agenti social non compaiono nelle viste degli agenti di Crypto City. La
configurazione AI utile agli agenti resta raggiungibile dalle Impostazioni.
Le Conferme continuano a usare i comandi esistenti per le decisioni del proprietario.

Questa pulizia riguarda la presentazione. Le route dirette delle pagine precedenti
(`office.html`, `sales.html`, `sims.html`, `ai.html`) e gli hash operativi storici
restano disponibili per compatibilità, anche quando il menu non li propone più.
Senza JavaScript, la home indica che occorre attivarlo per aprire le sale.
Motore, API, integrazioni, stato, strategie, audit, policy e workflow restano intatti;
gli ordini reali continuano a richiedere l'approvazione esplicita del proprietario.

`CRYPTO_CITY_SOURCE_SNAPSHOT.json` conserva la baseline originale, senza riscriverne
gli hash. Rispetto ai suoi 122 percorsi, **114 restano identici byte per byte** e
otto differiscono per le modifiche autorizzate all'interfaccia:

- `dashboard/index.html` e `dashboard/ai.html`;
- `dashboard/manifest.webmanifest` e `dashboard/sw.js`;
- `dashboard/icon-192.png`, `dashboard/icon-512.png`,
  `dashboard/icon-maskable-512.png` e `dashboard/apple-touch-icon.png`.

Il nuovo `dashboard/city-icon.svg` è la sorgente dell'icona. Il nome della cache
del service worker cambia per consentire all'app di caricare l'interfaccia aggiornata;
le API continuano a essere escluse dalla cache. I risultati di verifica riportati
nelle sezioni precedenti documentano le versioni precedenti alla pulizia.

Verifica della pulizia: 179 test unitari eseguiti, 177 superati e 2 saltati per
Pillow facoltativo; tutti i 16 scenari browser superati. I due nuovi scenari
verificano navigazione desktop, esclusione degli agenti social, configurazione AI,
menu mobile e accesso alle conferme del proprietario senza inviare comandi.
Le risposte mercato e attività dei test browser sono fixture dichiarate;
lo stato usa l'API autenticata del server reale. Nessun errore JavaScript non
gestito e nessuna richiesta di scrittura durante la navigazione.

`downloads/Crypto-City-INTERFACCIA.zip` contiene nove file frontend e le istruzioni.
CRC, elenco dei file e identità dei payload rispetto ai sorgenti sono verificati.
Una prova di applicazione con stato personalizzato conserva byte per byte stato,
motore, server, policy e launcher. I quattro pacchetti precedenti includono la
pagina aggiornata, con installatori e altri file invariati. La copia originale
di Crypto Machine resta pulita. L'applicazione della nuova ZIP sul PC dell'utente
deve ancora essere eseguita.
