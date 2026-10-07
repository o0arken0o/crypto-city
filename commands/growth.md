---
description: Esegue un ciclo del team rendite (staking, stablecoin, airdrop legittimi, portafoglio), rispettando budget, pause e approvazioni. I soldi li sposta solo il proprietario.
allowed-tools: Bash, Read, Glob, Agent, Task
---
Esegui UN ciclo del team rendite agendo come yield-lead (ruolo e priorità in agents/yield-lead.md, regole in POLICY.md). Sii breve.

1. `mm apply` poi `mm can-run --team rendite --force`. Se non è OK: `mm end-cycle --summary "saltato: <motivo>"` e termina.
2. `mm growth-brief` → è il tuo unico contesto.
3. Al massimo 2 deleghe (in parallelo se indipendenti) a: yield-scout, airdrop-scout, portfolio-analyst, ethics-guard. Mai agenti in pausa.
4. Prima di ogni richiesta di approvazione fai verificare l'oggetto da ethics-guard; se FAIL, non chiedere.
5. Chiudi con il resoconto per il proprietario (compare in plancia come "Team rendite"):
   `mm report '{"team":"rendite","headline":"…","done":["…"],"next":["…"],"needs_you":["…"]}'`
   - Italiano semplice, MAI codici interni (opp_…, apr_…, blk_…) né nomi di strumenti.
   - needs_you: solo azioni concrete del proprietario (es. "Decidi in plancia la proposta su USDC in Aave").
   - Il PASS di ethics-guard NON è l'approvazione del proprietario.
   - Un solo comando `mm report '…'`, niente heredoc o pipe; ogni apostrofo come \u0027.

Output finale: massimo 5 righe. Istruzioni extra dell'utente (opzionali): $ARGUMENTS
