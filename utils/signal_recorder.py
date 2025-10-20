import pandas as pd
import json
import os
from loguru import logger

class SignalRecorder:
    def __init__(self, save_type="csv", save_path="signals.csv", config=None):
        self.save_type = save_type
        self.save_path = save_path
        self.config = config if config else {}
        self.buffer = []

    def record(self, symbol, tf, strategy, signal, timestamp=None, meta=None):
        row = {
            "timestamp": timestamp if timestamp else pd.Timestamp.now(),
            "symbol": symbol,
            "tf": tf,
            "strategy": strategy,
            "signal": signal,
            "meta": meta if meta else {}
        }
        self.buffer.append(row)
        try:
            if self.save_type == "csv":
                self._save_csv(row)
            elif self.save_type == "json":
                self._save_json(row)
            elif self.save_type == "sql":
                self._save_sql(row)
            else:
                logger.warning(f"Unknown save_type: {self.save_type}")
        except Exception as e:
            logger.error(f"SignalRecorder save error: {e}")

    def _save_csv(self, row):
        # Tallennus CSV:hen, lisää rivi tiedoston loppuun
        df = pd.DataFrame([row])
        if not os.path.exists(self.save_path):
            df.to_csv(self.save_path, index=False, mode="w", header=True)
        else:
            df.to_csv(self.save_path, index=False, mode="a", header=False)

    def _save_json(self, row):
        # Tallennus JSON-tiedostoon, append-moodi
        if not os.path.exists(self.save_path):
            with open(self.save_path, "w") as f:
                json.dump([row], f, default=str)
        else:
            with open(self.save_path, "r+") as f:
                try:
                    data = json.load(f)
                except Exception:
                    data = []
                data.append(row)
                f.seek(0)
                json.dump(data, f, default=str)
                f.truncate()

    def _save_sql(self, row):
        # Placeholder: toteuta SQL-tallennus configin mukaan
        logger.info(f"SQL save not implemented: {row}")

    def get_signals(self, symbol=None, tf=None, strategy=None, start=None, end=None):
        # Lataa tallennetut signaalit
        if self.save_type == "csv":
            if not os.path.exists(self.save_path):
                return pd.DataFrame()
            df = pd.read_csv(self.save_path)
        elif self.save_type == "json":
            if not os.path.exists(self.save_path):
                return pd.DataFrame()
            with open(self.save_path, "r") as f:
                data = json.load(f)
            df = pd.DataFrame(data)
        else:
            df = pd.DataFrame(self.buffer)

        if symbol:
            df = df[df["symbol"] == symbol]
        if tf:
            df = df[df["tf"] == tf]
        if strategy:
            df = df[df["strategy"] == strategy]
        if start:
            df = df[df["timestamp"] >= pd.to_datetime(start)]
        if end:
            df = df[df["timestamp"] <= pd.to_datetime(end)]
        return df.reset_index(drop=True)
