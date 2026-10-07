---
description: Avvia la plancia di controllo web della Crypto Machine su http://localhost:8787
allowed-tools: Bash
---
Avvia in background `python3 "$MM_ROOT/dashboard/server.py"` (se MM_ROOT non è impostata usa `python3 dashboard/server.py`). Poi comunica l'URL http://localhost:8787 (porta modificabile con MM_PORT).
