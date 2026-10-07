---
description: Esegue un ciclo del team social (post pronti per Instagram, TikTok, LinkedIn e Facebook sulle strategie con risultati veri), rispettando budget, pause e limite di 3 post a settimana. I post li pubblica il proprietario.
allowed-tools: Bash, Read, Glob, Agent, Task
---
Esegui UN ciclo del team social agendo come social-lead (ruolo e priorità in agents/social-lead.md, regole in POLICY.md). Sii breve.

1. `mm apply` poi `mm can-run --team social --force`. Se non è OK: `mm end-cycle --summary "saltato: <motivo>"` e termina.
2. `mm social-brief` → è il tuo unico contesto.
3. Al massimo 3 deleghe (una per agente, in quest'ordine): social-writer, visual-designer, ethics-guard. Mai agenti in pausa.
   Se il brief ha "DA COMPLETARE PRIMA DI TUTTO", finisci quel post invece di iniziarne uno nuovo.
4. Prima di aprire il blocco "Pubblica il post …" fai verificare la cartella del post da ethics-guard; se FAIL, non aprirlo.
5. Chiudi con il resoconto per il proprietario (compare in plancia come "Team social"):
   `mm report '{"team":"social","headline":"…","done":["…"],"next":["…"],"needs_you":["…"]}'`
   - Italiano semplice, strategie per nome, MAI codici interni (opp_…, apr_…, blk_…) né nomi di strumenti.
   - needs_you: solo azioni concrete del proprietario (es. "Pubblica su Instagram il carosello sul trend di BTC").
   - Il PASS di ethics-guard NON è l'approvazione del proprietario.
   - Un solo comando `mm report '…'`, niente heredoc o pipe; ogni apostrofo come \u0027.

Output finale: massimo 5 righe. Istruzioni extra dell'utente (opzionali): $ARGUMENTS
