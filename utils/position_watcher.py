import time
from tools.capital_client import CapitalClient

# varmista että client on oikea CapitalClient, ei placeholder
try:
    if 'client' not in globals() or client is ... or not hasattr(client, "get_positions"):
        client = CapitalClient()
except Exception:
    client = CapitalClient()

class PositionWatcher:
    def __init__(self, check_interval=30):
        self.check_interval = check_interval

    def start(self):
        print("[INFO] PositionWatcher started")
        while True:
            try:
                positions = client.get_positions()
                print(f"[INFO] Open positions: {len(positions)}")
            except Exception as e:
                print(f"[ERROR] PositionWatcher: {e}")
            time.sleep(self.check_interval)
