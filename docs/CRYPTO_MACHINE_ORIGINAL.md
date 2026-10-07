# 📈 Crypto Machine

Plugin per **Claude Code** con tre team di agenti AI dedicati alle crypto: studiano i mercati, trasformano le idee in
strategie con regole precise, le **mettono alla prova** (backtest con costi, poi paper trading con prezzi veri e soldi
finti) e ti propongono di usarle con soldi veri **solo** quando hanno superato le prove. Plancia di controllo con
tre sale 3D, avvisi su Telegram, approvazione umana su tutto.

> Aspettative oneste: nessun agente garantisce guadagni e le crypto possono perdere molto valore in poco tempo.
> Questa macchina serve a **non** buttare soldi su idee non provate. Non ha chiavi di exchange e non invia ordini:
> quando una strategia approvata da te cambia posizione, ti arriva un **segnale** e decidi tu se eseguirlo.
> Non è un consiglio finanziario.

## Come funziona

```
            ┌──────────── plancia (dashboard/) ─────────────┐
            │ risultati · segnali · approvazioni · agenti · │
            │ strategie · pipeline · registro · direttive   │
            └───────────────┬───────────────────────────────┘
                 comandi → state/inbox.jsonl (o issue GitHub "mm: …")
                            ▼
 engine/mm.py  ── motore deterministico: stato, punteggi, UCB, budget ── 0 token
 scripts/       ── prezzi pubblici, backtest, paper trading, rendimenti ── 0 token
                            ▼  brief compatto (~40 righe)
 CEO (team trading)  ── max 2 deleghe ──► market-scanner · quant-analyst · onchain-analyst · quant-dev · risk-manager · ethics-guard
 yield-lead (rendite) ─────────────────► yield-scout · airdrop-scout · portfolio-analyst · ethics-guard
 social-lead (social) ─────────────────► social-writer · visual-designer · ethics-guard
```

**Pipeline di una strategia:** `idea → backtest → paper trading (≥ 14 giorni) → da approvare → live (segnali) → scaling`
oppure `scartata`. Il motore controlla i file: senza backtest PASS niente paper trading, senza il tuo ok niente live.

**Il backtest** (`scripts/backtest.py`) è deterministico: scarica le candele pubbliche (Coinbase, Kraken), simula con
commissioni e slittamento, divide il periodo in in-sample (70%) e out-of-sample (30%) e dà un verdetto:
PASS solo se nell'out-of-sample guadagna con Sharpe ≥ 0,5, drawdown ≤ 35%, almeno 8 operazioni e meno rischio del
semplice "compra e tieni". La strategia vede solo il passato, niente sbirciate nel futuro.

**Il paper trading** (`scripts/paper.py`, workflow `Crypto pulse`, ogni ora) fa girare le strategie con prezzi veri e
1000 $ finti. Le strategie che approvi per il live (con un capitale massimo) generano **segnali** su Telegram e in plancia:
"COMPRA · Trend BTC: porta BTC al 100% (≈ 150 € dei 150 € approvati)". I risultati reali li registri tu.

**Strategie** (i "bracci" del bandit UCB1): `trend-following`, `mean-reversion`, `momentum-rotation`, `smart-dca`,
`volatility-regime`, `yield-staking`. Solo spot, senza leva né short.

**Risparmio token:** calcoli, backtest e paper trading in Python (0 token); il CEO legge solo il brief; modelli
economici (haiku) per ricerca e controlli; tetto rigido per ciclo e per giorno.

**Guardia:** `scripts/guard.py` fotografa lo stato prima del turno degli agenti e annulla dopo tutto ciò che solo tu
puoi fare: approvazioni decise, `products/*/live.json` creati, risultati registrati o segnali scritti dagli agenti.

**Regole:** [POLICY.md](POLICY.md) è vincolante: niente leva, derivati, memecoin, presale, airdrop con più account,
chiavi o seed, promesse di guadagno, spam.

## I tre team e le tre sale 3D

| Piano | Sala | Team | Cosa vedi |
|---|---|---|---|
| 1 | 📈 **Sala trading** (`office.html`) | CEO, Market Scanner, Quant, On-chain, Quant Dev, Rischio, Etica | globo con i mercati, nastro con le strategie nelle fasi idea → backtest → paper → live, stampante dei backtest, slot machine per avviare un ciclo |
| 2 | 🏦 **Sala rendite** (`sales.html`) | Yield Lead, Yield Scout, Airdrop Scout, Portafoglio, Etica | distributore con i migliori rendimenti di staking/stablecoin (dati DefiLlama), muro con le note di ricerca, bacheca delle proposte da decidere, cassaforte con i risultati reali |
| 3 | 📱 **Sala social** (`social.html`) | Social Lead, Writer, Grafico, Etica | telefono gigante con i post pronti, colonne per social, set fotografico |

In ogni sala, sopra il grande schermo, scorre un **tabellone LED con i prezzi veri** di BTC, ETH e SOL in euro
(Coinbase, aggiornati ogni minuto; `MM_TICKER=BTC,ETH,SOL,…` per cambiarli). Le sale sono i tre piani di un palazzo
con ascensore di vetro, meteo vero della tua città (`MM_CITY`), giorno e notte, il gatto dell'ufficio. Anteprima: `?demo=1`.

## Installazione

```bash
# in Claude Code
/plugin marketplace add o0arken0o/crypto-machine
/plugin install crypto-machine@crypto-machine-marketplace
```

| Comando | Cosa fa |
|---|---|
| `/crypto-machine:cycle` | un ciclo del team trading |
| `/crypto-machine:growth` | un ciclo del team rendite |
| `/crypto-machine:social` | un ciclo del team social |
| `/crypto-machine:status` | brief e KPI, senza spendere in cicli |
| `/crypto-machine:command metti in pausa il risk-manager` | comando in linguaggio naturale |
| `/crypto-machine:dashboard` | avvia la plancia |

## Farlo girare da solo (GitHub Actions)

1. Settings → Secrets → Actions: `CLAUDE_CODE_OAUTH_TOKEN` (da `claude setup-token`) oppure `ANTHROPIC_API_KEY`;
   in alternativa o in aggiunta chiavi di altri provider (Groq, Gemini, OpenAI, …: vedi sotto).
   Facoltativo: `TELEGRAM_BOT_TOKEN` per segnali e avvisi sul telefono (si può salvare anche dalla plancia).
2. Workflow:
   | Workflow | Quando | Cosa fa |
   |---|---|---|
   | `Crypto cycle` | 4 volte a notte | team trading |
   | `Crypto rendite` | 1 volta a notte | dati DefiLlama + team rendite |
   | `Crypto social` | 1 volta a notte | team social (max 3 post a settimana) |
   | `Crypto pulse` | ogni ora | paper trading, segnali, Telegram (niente AI, < 1 minuto) |
   | `Crypto commands` | a ogni comando dalla plancia | approvazioni, go-live, stop |
3. Per fermare: variabili `MM_CRON_ENABLED=false`, `MM_GROWTH_ENABLED=false`, `MM_SOCIAL_ENABLED=false`,
   `MM_PAPER_ENABLED=false`, oppure "Metti in pausa" dalla plancia.

In locale: `scripts/run-forever.sh 60`, oppure in Claude Code `/loop 2h /crypto-machine:cycle`.

## Plancia di controllo

```bash
python3 dashboard/server.py        # http://127.0.0.1:8787
```
Home: risultati reali, **segnali delle strategie live**, cosa tocca a te, ultimo resoconto, la settimana.
Strategie: pipeline e risultati per strategia. Da fare: approvazioni (con il capitale massimo in evidenza) e blocchi.
Soldi: registro dei risultati reali (trading, staking, airdrop), riepilogo fiscale, budget AI.
Opzioni: `MM_PORT`, `MM_HOST`, `MM_TOKEN` (password).

**Online su Railway (per il telefono):** `railway.json` è pronto. Variabili: `MM_TOKEN` (≥ 12 caratteri),
`MM_GITHUB_REPO=o0arken0o/crypto-machine`, `MM_GITHUB_TOKEN` (fine-grained, solo questo repo: Contents read,
Issues read/write, Actions read/write, Secrets read/write). La radice `/` è il sito pubblico, la plancia è su `/plancia`.

## Budget di partenza
3 $/giorno di AI, 0,5 $ per ciclo. Modalità risparmio: dopo 10 $ di AI senza nessun guadagno registrato in 30 giorni,
massimo 2 $ al giorno. Il paper trading non costa nulla.

## Fisco (Italia)
Dal 2026 le plusvalenze sulle cripto-attività sono tassate al 33%, le crypto vanno nel quadro RW e gli exchange UE
comunicano le operazioni al Fisco (DAC8). `mm fisco` riassume i risultati dell'anno. Non è consulenza: senti il commercialista.

## Sviluppo
```bash
python3 -m unittest discover tests
python3 engine/mm.py brief
```
Contesto completo: [docs/AI_CONTEXT.md](docs/AI_CONTEXT.md). Guida passo-passo: [GUIDA.md](GUIDA.md).

## AI multi-provider e cascata
Il runner usa più API in cascata (Groq, OpenAI, Anthropic, Gemini, Cerebras, OpenRouter, Together, Mistral, DeepSeek,
xAI; anche più chiavi per provider: `GROQ_API_KEY_1`, …). Se Claude finisce la quota, lo stesso ciclo riparte con
l'orchestratore. Variabili: `MM_FREE_ONLY`, `MM_PROVIDER_ORDER`, `MM_MAX_TURNS`, `MM_MAX_OUTPUT_TOKENS`.
