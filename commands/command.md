---
description: Invia un comando alla Crypto Machine (es. "metti in pausa il risk-manager", "approva apr_x", "punta su trend-following", "registra guadagno 29€ da Kraken per opp_x").
allowed-tools: Bash
argument-hint: <istruzione in linguaggio naturale>
---
Traduci l'istruzione in UNO o più comandi JSON e accodali con `mm enqueue '<json>'`, poi esegui `mm apply`.
Formati:
- {"op":"system","args":{"state":"running|paused"}}
- {"op":"agent","args":{"name":"market-scanner","status":"active|paused","weight":0-5}}
- {"op":"strategy","args":{"name":"trend-following","status":"active|paused","weight":0-5}}
- {"op":"approval","args":{"id":"apr_x","decision":"approved|rejected","note":"..."}}
- {"op":"opportunity","args":{"id":"opp_x","stage":"killed|live|scaling|..."}}
- {"op":"directive_add","args":{"text":"..."}} / {"op":"directive_remove","args":{"id":"dir_x"}}
- {"op":"budget","args":{"usd_per_day":3,"usd_per_cycle":0.5,"cash_spend_limit_eur":0}}
- {"op":"ledger","args":{"type":"revenue|cost","amount_eur":29,"source":"Kraken","kind":"trading|staking|airdrop|altro","opportunity":"opp_x"}}

Istruzione: $ARGUMENTS
