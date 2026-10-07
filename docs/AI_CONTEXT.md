# AI Context — Crypto Machine

Contesto per qualsiasi AI o sviluppatore che modifica questo repo. Nasce come versione crypto della Money Machine
(stessa architettura: motore deterministico, team di agenti, guardia, plancia, sale 3D, workflow); qui c'è ciò che il
codice fa davvero. Aggiornalo quando cambi architettura, agenti o flussi. Ultimo aggiornamento: 3 ottobre 2026.

## 1. Cos'è
Un plugin Claude Code multi-agente che cerca strategie crypto, le **prova** con backtest e paper trading su prezzi
pubblici reali e propone al proprietario di usarle con soldi veri solo dopo le prove. Il repo è plugin e spazio di lavoro.

Principi non negoziabili:
1. POLICY.md è vincolante per ogni agente.
2. **Nessun ordine automatico, nessuna chiave di exchange.** Le strategie live producono segnali; il proprietario esegue a mano.
3. Percorso obbligatorio: backtest PASS → ≥ 14 giorni di paper trading → risk-manager → approvazione `golive` con capitale massimo.
4. Numeri veri solo dagli script deterministici; nel ledger solo risultati reali registrati dal proprietario.
5. Token = denaro: brief corti, deleghe limitate, cicli saltati quando non c'è niente di nuovo.

## 2. Architettura
| Componente | Percorso | Ruolo |
|---|---|---|
| Motore | `engine/mm.py` | Stato, punteggi, UCB1, budget, ledger, approvazioni, blocchi, lezioni, segnali, housekeeping, brief. Solo stdlib, 0 token. |
| Prezzi | `scripts/market_data.py` | Candele chiuse da Coinbase Exchange (paginato) con fallback Kraken; cache `state/market/<PAIR>-<TF>.json`. Binance non è usata (451 dagli USA, dove girano le Actions). Timeframe 1h, 6h, 1d. |
| Backtest | `scripts/backtest.py` | `products/<id>/strategy.py` (`PAIR`, `TIMEFRAME`, `PARAMS`, `target(c, p) → 0..1`), visione solo del passato (liste tagliate), costi 0,10% + 0,05%, split 70/30, verdetto PASS/FAIL con regole fisse, `backtest.json` + `media/01-backtest.png`. |
| Paper trading | `scripts/paper.py` | Ogni ora (workflow `Crypto pulse`) per le strategie in building/live/scaling: portafoglio virtuale da 1000 $, parte dall'ultima candela (niente operazioni nel passato), `paper.json` + `media/02-paper.png`. Per le strategie con `live.json` ogni cambio di esposizione diventa `mm signal`. |
| Rendimenti | `scripts/yields.py` | DefiLlama pools con filtri prudenti (TVL ≥ 50 M$, un solo asset, niente IL, APY 30gg 1-25%) → `state/research/yields-<data>.md` e `state/market/yields.json`. |
| Azioni | `scripts/actions.py` | Dopo l'ok: `golive` scrive `products/<id>/live.json` (serve `capital_eur`), `stop` lo sposta in `live-stopped.json` e riporta a building; `site`, `linkedin` come nella Money Machine. |
| Guardia | `scripts/guard.py` | Annulla ciò che gli agenti non possono fare: decidere approvazioni, creare `site/*/.approved` o `products/*/live.json`, registrare risultati, scrivere segnali. |
| Telegram | `scripts/telegram.py` | Segnali (📈), risultati registrati, cose da decidere, resoconti, cicli saltati/falliti, riepilogo settimanale. |
| Plancia | `dashboard/` | `server.py` (API, `/api/prices` per il tabellone LED, `/api/weather`, sito pubblico), `index.html`, sale 3D `office.html` (trading) e `sales.html` (rendite), guscio comune in stile exchange in `exchange.js` (che usa `scene3d.js`). |
| Workflow | `.github/workflows/` | `crypto-cycle.yml`, `crypto-rendite.yml`, `crypto-social.yml`, `crypto-pulse.yml` (orario), `crypto-commands.yml`, `tests.yml`, `pages.yml`. |

Chiavi interne mantenute dalla Money Machine per compatibilità: le fasi `validating` (= backtest) e `building`
(= paper trading); il comando `growth-brief` e `/crypto-machine:growth` sono il team rendite; la cartella di una
strategia è `products/<id>/`.

## 3. Agenti
Team trading (`ceo`): market-scanner (haiku), quant-analyst (sonnet), onchain-analyst (haiku), quant-dev (sonnet),
risk-manager (haiku), ethics-guard (haiku).
Team rendite (`yield-lead`, sonnet): yield-scout (haiku), airdrop-scout (haiku), portfolio-analyst (sonnet), ethics-guard.
Team social (`social-lead`, sonnet): social-writer (sonnet), visual-designer (haiku), ethics-guard.

## 4. Housekeeping (engine/mm.py)
- `live`/`scaling` senza `live.json` approvato (o senza risultati reali nel ledger) → torna a building/validating.
- `live.json` approvato → `live`. `building` senza backtest PASS → `validating`.
- Check "DA SISTEMARE": backtest PASS ancora in validating (`to_paper`), paper ≥ 14 giorni senza richiesta golive (`unpublished`).
- Controlli d'ingresso (`opp_problem`): `mm opp` rifiuta opportunità senza titolo, fasi inesistenti e id non validi;
  `awaiting_approval` senza una richiesta di approvazione aperta torna indietro alla pulizia di inizio ciclo.
- Limite lavori: con check aperti o ≥ 3 strategie in backtest il motore rifiuta nuovi mercati/strategie degli agenti.

## Regole del backtest (versione 2, ottobre 2026)
Oltre a guadagno/Sharpe/drawdown/operazioni/meno rischio del hold: almeno 1 anno di prezzi (`storia_1_anno`, download
`LIMIT` per timeframe, cache fino a 10000 candele) e `vale_il_rischio` (out-of-sample ≥ metà del guadagno del buy & hold
o Sharpe migliore; se il mercato scende, perdere meno). `backtest.json` ha `"rules": 2`; le strategie con regole più
vecchie tornano in backtest alla pulizia di inizio ciclo (`BACKTEST_RULES` in mm.py). quant-dev implementa tutte le regole
(stop compresi), risk-manager lo verifica. "Avvia ciclo" in plancia rifiutato se lo stesso team è partito da < 30 minuti.

## Universo dei mercati
Solo BTC, ETH, SOL, XRP, ADA, CRO (`MARKETS` in `scripts/market_data.py` e `engine/mm.py`, coppie della plancia in `server.py`).
Il backtest rifiuta qualsiasi altra coppia (niente memecoin o token piccoli). Il brief del CEO elenca le monete senza analisi
negli ultimi 14 giorni (`uncovered_markets`) e il market-scanner ne copre almeno una per ciclo. Rendite: staking anche su ADA e CRO.

## Avvio automatico dei cicli
Il cron di GitHub è inaffidabile (ritardi di ore, avvii saltati). La plancia online (`server.py`, `autostart_loop`, solo in modalità GitHub)
avvia lei i workflow all'orario previsto (`AUTOSTART`: trading 22/0/2/4:17 UTC, rendite 23:47 UTC, pulse ogni ora :23), con input `auto=1`,
una volta per orario e solo se il workflow non è già partito. I cron restano come riserva: il job `gate` li salta se c'è già stato un avvio
recente. Gli avvii automatici rispettano `MM_CRON_ENABLED`/`MM_GROWTH_ENABLED` e possono saltare se non c'è niente da fare (come il cron).
Spegnimento: variabile `MM_AUTOSTART=false` su Railway.

## 5. Sale 3D
La home privata `/plancia` è **Crypto City** (`dashboard/index.html`, vista `#city`): città 3D
procedurale con dodici edifici cliccabili e sale di dettaglio `#city/<id>`. Le sei sale trader BTC/ETH/SOL/XRP/ADA/CRO
sono viste dei mercati e delle strategie esistenti, non nuovi agenti. Le altre sale rappresentano
market-scanner, quant-analyst, risk-manager, portfolio-analyst, yield-lead/yield-scout e ceo.
Codice inline isolato e Three.js locale; letture dalle API attuali, senza comandi, ordini o cicli avviati
dalla navigazione. Dati mancanti, snapshot statici e connessione interrotta sono espliciti; fallback
HTML delle dodici sale per errori dei moduli o WebGL. P&L attribuito solo alle voci ledger delle
strategie associate, performance backtest/paper separate, orari programmati in Europe/Rome.
`#oggi` conserva il terminale e tutte le sezioni operative restano accessibili; `/` resta il sito pubblico.
Mappa completa e confini protetti: [CRYPTO_CITY_ARCHITECTURE.md](CRYPTO_CITY_ARCHITECTURE.md).

Piano 1 sala trading (`office.html`, ricostruita in stile exchange, scena propria): stanza ad angolo blu notte, globo olografico con i mercati (punti dorati), pista luminosa Idea → Backtest → Paper trading → Live con le strategie come blocchi, scrivanie degli agenti lungo le pareti, schermi con candele e KPI veri, vetrina di monete; pannelli a sinistra (KPI, Avvia ciclo) e a destra (Cosa succede, resoconto del CEO).
Piano 2 sala rendite (`sales.html`, stile exchange): moneta olografica al centro e colonne di luce, una per rendimento reale di `yields.json` (altezza = APY 30 giorni, azzurro stablecoin, viola BTC/ETH/SOL), parete con note di ricerca `state/research/{yield,staking,airdrop,portfolio}*.md` e proposte "tocca a te", schermo con risultati e proposte da decidere.
Sala social rimossa (ottobre 2026): il team social resta ma il suo ciclo programmato è spento (solo avvio a mano). Plancia (`index.html`) in stile exchange (vetro blu notte, griglia, accento blu) con un terminale di trading in Oggi (barra prezzi, lista mercati BTC/ETH/SOL in EUR, grafico a candele con volumi 15m/1h/1g e statistiche 24h, order book e ultimi scambi da `/api/trades`, tutto pubblico Coinbase, solo da guardare). Le sale precedenti usano `charts.js`; la home Crypto City e il terminale Oggi incorporano gli stessi helper in `city-charts` (`CryptoCityCharts`), per funzionare anche con copie Windows prive del modulo o della route `/charts.js`. Pareti delle sale (`room.panel` in `exchange.js`): striscia LED in alto con prezzi (`/api/prices`) e notizie del ciclo; trading: order book BTC (`/api/orderbook`, Coinbase), orologi delle borse, paura/avidità (`/api/feargreed`, alternative.me), bacheca strategie, registro segnali (`world.signals`); rendite: semaforo del rischio automatico (APY, depositi, premi: non è un audit), cassaforte con i risultati reali, risultati per mese (`world.months`), airdrop (note `state/research/airdrop*`). Vista condivisibile con `?cam=x,y,z,tx,ty,tz`. Grafici delle sale con candele reali da `/api/candles` (Coinbase Exchange, coppie BTC/ETH/SOL in EUR/USD ammesse, cache 60 s, aggiornati ogni minuto; senza dati scrivono "dati non disponibili"). Quattro pareti che si nascondono se stanno tra camera e stanza, una lampada su ogni agente. Agenti come persone (`person()` in `exchange.js`: viso con occhi che sbattono, naso, bocca, orecchie, sei tipi di capelli, occhiali/barba casuali ma fissi per agente, giacca nel colore dell'agente, braccia, mani, gambe, scarpe): al lavoro siedono e scrivono guardando i monitor, in pausa sono assopiti; a riposo ogni tanto si alzano, camminano lungo i corridoi davanti alle scrivanie fino a un collega vicino e chiacchierano (fumetti bianchi: prezzi veri della striscia LED, titolo vero dell'ultimo resoconto, ultimo lavoro vero del collega, orario del prossimo ciclo o frasi di ufficio), poi tornano alla sedia (`life` in `createRoom`, una coppia alla volta; un compito, la pausa o la festa li richiama subito). Agenti della parete sinistra girati verso la stanza. Sala trading: tabellone LED dei prezzi (`priceTicker` in `scene3d.js`, `/api/prices`, `MM_TICKER`). Festa del primo guadagno in entrambe (`firstSaleParty`). Demo `?demo=1`.
three.js 0.170 è incluso in `dashboard/vendor/three/` (servito da `server.py` su `/vendor/three/…`): le sale non dipendono da un CDN.
Tema `neon` (opzione `theme` di `room()` in `scene3d.js`, non più usato dalle sale nuove): pavimento blu notte con griglia, strisce LED, monitor con candele sulle pareti, sempre notte; scrivanie in vetro scuro (`THEME` in `workstation`). Accenti: trading 0x2f9bff, rendite 0x6c7cff, social 0x21d4fd.
`sims.html`: la "casa" isometrica stile The Sims con le tre sale affiancate e tutti gli agenti (canvas 2D, nessuna libreria). Legge `api/live?team=…`: chi lavora siede alla scrivania con un fumetto, gli altri girano per casa; senza dati va in demo.

## 6. Fisco (Italia, ottobre 2026)
Plusvalenze su cripto-attività al 33% dal 2026 (26% nel 2025), quadro RW, DAC8. `mm fisco` e GUIDA.md. Non è consulenza.

## 7. Come modificare il sistema
- Nuovo agente: `agents/<nome>.md` → `AGENTS` e `TEAM_AGENTS` in `engine/mm.py` → capo team e comando → sala 3D.
- Nuova regola di backtest: `RULES` in `scripts/backtest.py` (e test in `tests/test_crypto.py`).
- Nuova azione esterna: sempre dietro un'approvazione con `channel`, eseguita da `scripts/actions.py`, marcatore protetto da `guard.py`.
- Test: `python3 -m unittest discover tests`.
