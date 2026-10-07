# Crypto Machine — note per Claude

- Questo repo è sia il plugin Claude Code (`.claude-plugin/`, `agents/`, `commands/`, `skills/`, `hooks/`, `bin/`, `engine/`) sia lo spazio di lavoro.
- Il file di stato `state/state.json` (e `state/inbox.jsonl`) si modifica SOLO tramite il comando `mm …`, mai a mano.
- Le strategie vivono in `products/<id>/`: `strategy.py` (la scrive il quant-dev), `backtest.json` e `paper.json`
  (li scrivono SOLO gli script), `live.json` (lo scrive SOLO scripts/actions.py dopo l'ok del proprietario), `media/`, `social/`.
- Numeri veri solo dagli script deterministici: `scripts/market_data.py`, `scripts/backtest.py`, `scripts/paper.py`, `scripts/yields.py`.
- Nessun ordine automatico, nessuna chiave di exchange, niente leva. POLICY.md è vincolante e non negoziabile.
- Test: `python3 -m unittest discover tests`.
- Contesto completo: `docs/AI_CONTEXT.md`. Aggiornalo quando cambi agenti o flussi.
