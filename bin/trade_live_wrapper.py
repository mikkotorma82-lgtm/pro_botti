#!/usr/bin/env python3
import os, sys, subprocess
from tools.live_equity import get_account_summary

# hae live-equity
acc = get_account_summary()
eq = int(float(acc.get("equity", 0)))

# kokoa alkuperäinen komento: korvaa tools.trade_live kutsu lisäämällä --equity0 <eq>
cmd = [sys.executable, "-m", "tools.trade_live"]
# alkuperäisen launch-putken lisäargit tulevat stdinistä tai ympäristöstä – jos haluat
# kovakoodata, lisää tähän omat flagisi:
extra = os.environ.get("TRADE_LIVE_ARGS", "--config config/risk.yaml")
cmd.extend(extra.split())
cmd.extend(["--equity0", str(eq)])

print(f"[INFO] Launching tools.trade_live with live equity0={eq}")
sys.exit(subprocess.call(cmd))
