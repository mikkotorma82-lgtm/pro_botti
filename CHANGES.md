## 2025-10-14
- Add scripts/quick_evaluate_select.py (model-free evaluation + Top-5 selection)
- Add scripts/auto_retrain.sh (backfill → train → evaluate+select → optional live restart)
- Add scripts/live_start.sh wrapper that enforces using state/active_symbols.json
- Add deploy/pro_botti.service, pro_botti-retrain.service, pro_botti-retrain.timer
