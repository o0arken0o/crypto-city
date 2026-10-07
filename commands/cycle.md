---
description: Esegue un ciclo del team trading della Crypto Machine (mercati → strategie → backtest → paper trading → proposte di live), rispettando budget e pause.
allowed-tools: Bash, Read, Glob, Agent, Task
---
Esegui UN ciclo del team trading agendo come CEO (ruolo e priorità in agents/ceo.md, regole in POLICY.md). Sii breve.

1. `mm apply` (comandi dalla plancia) poi `mm can-run --force`. Se non è OK: `mm end-cycle --summary "saltato: <motivo>"` e termina.
2. `mm begin-cycle` → questo è il brief: è il tuo unico contesto.
3. Decidi al massimo 2 deleghe secondo le priorità del CEO e lanciale (in parallelo se indipendenti) ai sub-agenti:
   market-scanner, quant-analyst, onchain-analyst, quant-dev, risk-manager, ethics-guard. Mai agenti in pausa.
4. Prima di ogni richiesta di approvazione fai passare l'oggetto da ethics-guard; se FAIL, non chiedere.
5. Chiudi il ciclo con il resoconto per il proprietario (compare in cima alla plancia):
   `mm report '{"headline":"…","done":["…"],"next":["…"],"needs_you":["…"]}'`
   - Italiano semplice, per una persona non tecnica: chiama le strategie per nome, MAI codici interni (opp_…, mkt_…, apr_…).
   - headline: 1 frase (≤ 120 caratteri). done: 1-4 fatti concreti. next: 1-3 cose del prossimo ciclo e perché.
   - needs_you: solo azioni concrete del proprietario (es. "Decidi in plancia se passare al live la strategia Trend BTC con 150 €"); vuota se non serve nulla.
   - Sii esatto: backtest e paper trading NON sono soldi veri; il PASS di ethics-guard NON è l'approvazione del proprietario.
   - Un solo comando `mm report '…'`, niente heredoc, pipe o file temporanei. Ogni apostrofo come \u0027.

Output finale: massimo 5 righe. Istruzioni extra dell'utente (opzionali): $ARGUMENTS
