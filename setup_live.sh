#!/usr/bin/env bash
set -e
echo "🚀 CapitalBot Live Setup starting..."

cd /root/pro_botti

# 1️⃣ Virtuaaliympäristö
if [ ! -d "venv" ]; then
  echo "[SETUP] Creating Python virtual environment..."
  apt install -y python3-venv python3-pip git
  python3 -m venv venv
fi
source venv/bin/activate

# 2️⃣ Riippuvuudet
echo "[SETUP] Installing/upgrading dependencies..."
pip install --upgrade pip
pip install -U pandas numpy requests python-dotenv matplotlib scikit-learn xgboost lightgbm joblib

# 3️⃣ Hakemistot
mkdir -p logs data models reports
chmod -R 755 logs data models reports

# 4️⃣ Systemd-palvelu
echo "[SETUP] Configuring systemd service..."
cat > /etc/systemd/system/pro_botti.service <<'EOL'
[Unit]
Description=CapitalBot v6.11 - Live Trading Engine (Mikko Törmä)
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/pro_botti
EnvironmentFile=/root/pro_botti/secrets.env
ExecStart=/root/pro_botti/venv/bin/python -u main.py
Restart=always
RestartSec=5
StandardOutput=append:/root/pro_botti/logs/trader.log
StandardError=append:/root/pro_botti/logs/trader.log

[Install]
WantedBy=multi-user.target
EOL

systemctl daemon-reload
systemctl enable --now pro_botti.service

# 5️⃣ Auto Git push skripti
cat > tools/auto_push.py <<'PY'
#!/usr/bin/env python3
import subprocess, datetime
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
try:
    subprocess.run(["git", "add", "-A"], check=True)
    subprocess.run(["git", "commit", "-m", f"Auto update {now}"], check=False)
    subprocess.run(["git", "push", "origin", "main"], check=True)
    print(f"[{now}] ✅ Auto Git push done")
except Exception as e:
    print(f"[{now}] ⚠️ Auto push failed:", e)
PY
chmod +x tools/auto_push.py

echo "✅ Setup completed. Botti käynnissä ja valmis live-treidiin!"
