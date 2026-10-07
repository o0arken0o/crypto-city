# Guida: dalla prima strategia ai primi segnali

Questa macchina **non** ti fa diventare ricco: ti evita di mettere soldi su idee non provate. Lavora così:
gli agenti cercano idee → le testano (backtest) → le fanno girare con soldi finti (paper trading) → ti propongono
le migliori con un capitale massimo → tu decidi → ricevi i segnali e li esegui tu sul tuo exchange.

## Parte 0 — Una volta sola (circa 20 minuti)

- [ ] **Repo e chiave AI.** Crea il repo su GitHub (vedi README), poi Settings → Secrets → Actions:
      `CLAUDE_CODE_OAUTH_TOKEN` (comando `claude setup-token`) oppure una chiave gratuita come `GROQ_API_KEY`.
- [ ] **Telegram (consigliato).** Su Telegram apri @BotFather → `/newbot` → apri il tuo bot e premi Avvia.
      Incolla il token in plancia (Impostazioni → Avvisi su Telegram) oppure come secret `TELEGRAM_BOT_TOKEN`.
      Lì ti arrivano i segnali e le cose da decidere.
- [ ] **Plancia sul telefono.** Railway con `railway.json` (variabili nel README), poi "Aggiungi a schermata Home".
- [ ] **Dì alla macchina chi sei.** Plancia → Direttive, per esempio:
      "Ho un conto su Kraken. Capitale crypto totale circa 2.000 €. Al massimo 200 € per strategia. Solo BTC ed ETH."
      Senza queste informazioni il risk-manager propone al massimo 200 €.
- [ ] **Exchange.** Usa un exchange regolamentato nell'UE, a tuo nome, con 2FA. **Mai** dare a nessuno (agenti compresi)
      seed phrase, password o chiavi API con permessi di prelievo.

## Ogni giorno (2 minuti)

1. Apri la plancia o Telegram.
2. **Segnali** (solo strategie che hai approvato): "COMPRA/VENDI · <strategia>: porta BTC al X%". Se sei d'accordo, lo
   esegui tu sull'exchange. Se non sei d'accordo, ignoralo.
3. **Approvazioni:** leggi numeri e rischi, poi Approva o Rifiuta. Per il live scegli tu il capitale massimo.
4. **Risultati reali:** quando chiudi un'operazione o ricevi staking/airdrop, registralo in Soldi → Registro
   (tipo trading, staking, airdrop). Solo cifre vere: servono alla macchina per imparare e a te per il fisco.

## Team rendite (automatico, decidi tu)
Ogni notte legge i rendimenti pubblici (DefiLlama, filtri prudenti), verifica i migliori sulle fonti ufficiali e ti
propone al massimo una mossa (es. "200 € di USDC su un protocollo grande e di lunga data", con rischi e come uscire).
Airdrop: solo programmi ufficiali, un solo account. Mai leva, mai APY assurdi.

## Team social (automatico, pubblichi tu)
Prepara al massimo 3 post a settimana per raccontare in modo trasparente cosa testa la macchina, con i grafici veri.
Ogni post dice "Non è un consiglio finanziario". Li pubblichi tu dal tuo account.

## Cosa non devi fare (POLICY.md)
- Non dare chiavi, seed o password a nessuno. Non collegare bot che operano da soli.
- Non usare leva, futures, prestiti. Non investire soldi che non puoi permetterti di perdere.
- Non vendere "segnali" ad altri e non promettere guadagni nei post.

## Fisco (non è consulenza: senti il commercialista)
- Dal 2026 le plusvalenze sulle cripto-attività sono tassate al **33%** (26% nel 2025), senza franchigia.
- Le crypto vanno indicate nel **quadro RW** anche se non vendi; conserva lo storico completo delle operazioni.
- Staking e airdrop possono essere redditi: registra data, quantità e valore in euro.
- Dal 2026 gli exchange UE comunicano le operazioni all'Agenzia delle Entrate (**DAC8**).
- `mm fisco` o il riquadro in plancia riassume i risultati registrati dell'anno.

Fonti (ottobre 2026): Agenda Digitale, "Tassazione cripto-attività 2026"; Studio Zanovello, "Plusvalenze su
cripto-attività con tassazione al 33%".
