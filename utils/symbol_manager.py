import json
import os

class SymbolManager:
    def __init__(self, config=None):
        self.config = config if config else {}
        self.symbols = self.config.get("symbols", [])
        self.tfs = self.config.get("tfs", ["1h", "4h", "15m"])
        self.whitelist = set(self.config.get("whitelist", []))
        self.blacklist = set(self.config.get("blacklist", []))

    def load_symbols(self, path=None):
        if path and os.path.exists(path):
            with open(path, "r") as f:
                data = json.load(f)
                self.symbols = data.get("symbols", self.symbols)
                self.tfs = data.get("tfs", self.tfs)
        return self.symbols, self.tfs

    def add_symbol(self, symbol):
        if symbol not in self.symbols:
            self.symbols.append(symbol)

    def remove_symbol(self, symbol):
        if symbol in self.symbols:
            self.symbols.remove(symbol)

    def set_tfs(self, tfs_list):
        self.tfs = list(tfs_list)

    def is_active(self, symbol, tf=None):
        # Whitelist/blacklist-logiikka
        if self.whitelist and symbol not in self.whitelist:
            return False
        if self.blacklist and symbol in self.blacklist:
            return False
        return symbol in self.symbols and (tf is None or tf in self.tfs)

    def get_active_symbols(self, tf=None):
        # Palauttaa aktiiviset symbolit halutulla TF:llä
        return [s for s in self.symbols if self.is_active(s, tf)]

    def reload(self, path=None):
        return self.load_symbols(path)

    def as_dict(self):
        return {
            "symbols": self.symbols,
            "tfs": self.tfs,
            "whitelist": list(self.whitelist),
            "blacklist": list(self.blacklist)
        }
