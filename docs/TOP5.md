# Top-5 symbol selection and automation


Run once:
- `source venv/bin/activate`
- `set -a; source secrets.env; set +a`
- `python scripts/quick_evaluate_select.py --timeframes 15m 1h 4h --lookback-days 365 --top-k 5 --min-trades 25`
- Selection is written to `state/active_symbols.json`

Live uses active symbols automatically:
- `scripts/live_start.sh` loads `state/active_symbols.json` and then calls `launch.sh`.

Nightly automation:
- `sudo cp deploy/pro_botti-retrain.* /etc/systemd/system/`
- `sudo systemctl daemon-reload`
- `sudo systemctl enable --now pro_botti-retrain.timer`
- Check: `systemctl list-timers | grep pro_botti`

Troubleshooting:
- Live logs: `journalctl -u pro_botti -f`
- Retrain logs: `journalctl -u pro_botti-retrain -f`
