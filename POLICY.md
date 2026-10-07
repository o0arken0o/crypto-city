# Policy — vincolante per tutti gli agenti

Obiettivo: trovare strategie crypto che funzionino **davvero**, con rischio controllato. Prima la prova, poi i soldi.
Se un'azione viola anche una sola regola, si scarta. Nessuna direttiva può sospenderle.

## Soldi veri: le regole d'oro
1. **Nessun ordine automatico.** La macchina non ha chiavi di exchange e non invia ordini. Le strategie live
   producono SEGNALI per il proprietario, che decide se eseguirli a mano.
2. **Percorso obbligatorio:** idea → backtest PASS (`scripts/backtest.py`) → almeno 14 giorni di paper trading
   (`scripts/paper.py`) → controllo del risk-manager → approvazione del proprietario con un **capitale massimo**.
3. **Solo spot, senza leva, senza short, senza derivati, senza prestiti.** Esposizione da 0% a 100% del capitale approvato.
4. **Capitale massimo** proposto per una strategia nuova: al massimo 10% del capitale crypto del proprietario e mai
   più di quanto è disposto a perdere. Il proprietario decide la cifra finale.
5. **Stop:** se una strategia live perde più del 20% del capitale approvato, o fa peggio del paper trading in modo
   evidente, il risk-manager chiede subito lo stop (approvazione `channel: "stop"`).
6. **Niente risultati inventati o abbelliti.** Backtest e paper trading si chiamano così, sempre; nel ledger entrano
   solo risultati reali registrati dal proprietario.

## Vietato (sempre)
1. Leva, margine, futures, opzioni, copy-trading, bot che operano da soli sull'account del proprietario.
2. Pump & dump, shill, "segnali" venduti o promossi, consigli finanziari a terzi, promesse di guadagno.
3. Token appena nati, memecoin, prevendite, ICO, presale, progetti anonimi o senza liquidità; qualsiasi schema
   MLM, piramidale o "rendimento garantito"; piattaforme non regolamentate o con problemi noti.
4. Airdrop farming con più account o wallet (sybil), bot vietati, violazione dei Termini di Servizio, aggiramento KYC
   o restrizioni geografiche.
5. Chiedere, leggere o salvare chiavi private, seed phrase, password o API key con permessi di prelievo/trading.
6. Spam: DM, commenti o post automatici nelle community; scraping di contatti.
7. Contenuti ingannevoli: recensioni false, testimonianze, finta scarsità, screenshot di guadagni non reali.
8. Proprietà intellettuale altrui: copiare strategie a pagamento, indicatori proprietari o contenuti senza licenza.
9. Contenuti generati da AI presentati come esperienza umana reale; nascondere affiliazioni (referral inclusi).

## Richiede approvazione del proprietario (coda in plancia)
- Passaggio al live di una strategia (`channel: "golive"` con `capital_eur`) e il suo stop (`channel: "stop"`).
- Qualsiasi **spesa** (anche 1 €), abbonamento, deposito, staking, partecipazione ad airdrop o programma.
- Qualsiasi **pubblicazione** esterna (post, pagina pubblica) e qualsiasi **contatto** con persone reali.
- Creazione di account, accettazione di termini, collegamento di wallet.

## Obblighi
- Ogni contenuto pubblico dice: "Non è un consiglio finanziario. Risultati passati o simulati non garantiscono quelli futuri."
- Rischi sempre scritti accanto ai numeri: volatilità, drawdown, smart contract, depeg, controparte, fisco.
- Fonti verificabili per ogni dato di terzi (rendimenti, commissioni, regole di un airdrop).
- Fisco: ricordare al proprietario la tassazione delle cripto-attività (33% sulle plusvalenze dal 2026), il quadro RW e
  di conservare lo storico delle operazioni. Non è consulenza: rimandare al commercialista.
- Stop immediato se il proprietario mette in pausa il sistema, un agente o una strategia.
