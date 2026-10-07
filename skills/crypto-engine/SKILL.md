---
name: crypto-engine
description: Protocollo della Crypto Machine - come leggere il brief, registrare mercati, strategie, backtest, paper trading, approvazioni e risultati reali tramite il motore mm e gli script deterministici. Usala ogni volta che lavori su mercati, strategie o risultati della Crypto Machine.
---
# Crypto Engine

Il motore `mm` (wrapper di engine/mm.py, già nel PATH) è l'unica interfaccia verso lo stato. Usa sempre `mm …` così com'è: niente `python3 …/mm.py`, niente variabili `${…}` (verrebbero bloccate dai permessi). Non modificare mai state/state.json a mano.

| Scopo | Comando |
|---|---|
| Contesto compatto | `brief` (trading) · `growth-brief` (rendite) · `social-brief` |
| KPI JSON | `kpis` |
| Mercato (score 0-100 automatico) | `market '{"name","strategy","demand","ticket","speed","competition","confidence","evidence"}'` |
| Strategia/opportunità (score automatico) | `opp '{"title","market","strategy","expected_eur","confidence","cost_eur","effort_h","days_to_cash","rules",...}'` |
| Cambio fase | `stage <opp_id> <idea·validating·building·awaiting_approval·live·scaling·killed> --next "..."` |
| Richiesta approvazione | `approval '{"kind","title","detail","opportunity","cost_eur","ethics"}'`; `"channel":"golive","capital_eur":N` per il live (dopo l'ok la macchina scrive live.json e manda i segnali), `"channel":"stop"` per fermare |
| Risultato **reale** (lo registra il proprietario) | `ledger '{"type":"revenue·cost","amount_eur","source","opportunity","kind":"trading·staking·airdrop·altro"}'` |
| Totali dell'anno per il fisco | `fisco` |
| Blocco | `blocker '{"title","blocks":["opp_x"],"owner":"human·agent","how","link"}'` · risolto: `unblock <blk_id>` |
| Evento | `log <agente> "<messaggio>"` |
| Lezione per il futuro | `learn "<lezione>"` |
| Resoconto di fine ciclo | `report '{"headline","done":[],"next":[],"needs_you":[]}'` (con `"team":"rendite"` o `"social"` per gli altri team) |
| Allocazione strategie (UCB1) | `allocate` |

Aggiungi sempre `--agent <nome>` quando scrivi.

## Script deterministici (0 token, numeri veri)
| Script | Cosa fa |
|---|---|
| `python3 scripts/market_data.py BTC-USD 1d` | candele chiuse pubbliche (Coinbase, Kraken), cache in state/market/ |
| `python3 scripts/backtest.py products/<id>` | backtest con costi, in-sample/out-of-sample, verdetto PASS/FAIL, backtest.json + media/01-backtest.png |
| `python3 scripts/paper.py run` | paper trading orario (workflow Crypto pulse) e segnali delle strategie live |
| `python3 scripts/yields.py` | rendimenti DeFi/staking prudenti (DefiLlama) per il team rendite |

## Fasi
idea → **validating** = backtest → **building** = paper trading (serve backtest PASS) → awaiting_approval →
**live** = approvata dal proprietario con capitale massimo (solo segnali, esecuzione manuale) → scaling, oppure killed.

## Strategie (bracci del bandit)
trend-following · mean-reversion · momentum-rotation · smart-dca · volatility-regime · yield-staking.
L'UCB1 bilancia sfruttamento (risultati reali registrati) ed esplorazione, con prior dai punteggi dei mercati e peso umano dalla plancia.

## Punteggi
- Mercato: log((forza·liquidità·frequenza)/affollamento) × (0.5+0.5·confidenza) → 0-100.
- Strategia: (guadagno atteso × confidenza) / (costo + ore×15€ + 1) × 30/(giorni+30) → 0-100, serve solo a ordinare le idee: decide il backtest, non il punteggio.
