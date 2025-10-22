import pandas as pd
import numpy as np
import os

class DataLoader:
    def __init__(self, source_type="csv", config=None):
        self.source_type = source_type
        self.config = config if config else {}

    def load(self, symbol, tf="1h", start=None, end=None, features=None):
        method = getattr(self, f"_load_{self.source_type}", None)
        if not method:
            raise ValueError(f"Unsupported source_type: {self.source_type}")
        return method(symbol, tf, start, end, features)

    def _load_csv(self, symbol, tf, start, end, features):
        # Oletetaan tiedostopolku: data/{symbol}_{tf}.csv
        path = self.config.get("csv_path", f"data/{symbol}_{tf}.csv")
        if not os.path.exists(path):
            print(f"[DataLoader] File not found: {path}")
            return pd.DataFrame()
        df = pd.read_csv(path)
        df = self._filter(df, start, end, features)
        return df

    def _load_parquet(self, symbol, tf, start, end, features):
        path = self.config.get("parquet_path", f"data/{symbol}_{tf}.parquet")
        if not os.path.exists(path):
            print(f"[DataLoader] File not found: {path}")
            return pd.DataFrame()
        df = pd.read_parquet(path)
        df = self._filter(df, start, end, features)
        return df

    def _load_sql(self, symbol, tf, start, end, features):
        # Placeholder: toteuta SQL-haut configin mukaan
        return pd.DataFrame()

    def _load_api(self, symbol, tf, start, end, features):
        # Placeholder: toteuta API-haut configin mukaan
        return pd.DataFrame()

    def _load_mock(self, symbol, tf, start, end, features):
        # Luo dummy-datan testaukseen
        dates = pd.date_range(start="2022-01-01", periods=100, freq="H")
        df = pd.DataFrame({
            "timestamp": dates,
            "open": np.random.rand(100) * 100,
            "high": np.random.rand(100) * 101,
            "low": np.random.rand(100) * 99,
            "close": np.random.rand(100) * 100,
            "volume": np.random.rand(100) * 1000
        })
        df = self._filter(df, start, end, features)
        return df

    def _filter(self, df, start, end, features):
        # Suodata aikaväli ja featuret
        if start:
            df = df[df["timestamp"] >= pd.to_datetime(start)]
        if end:
            df = df[df["timestamp"] <= pd.to_datetime(end)]
        if features:
            keep = ["timestamp"] + [f for f in features if f in df.columns]
            df = df[keep]
        return df.reset_index(drop=True)
