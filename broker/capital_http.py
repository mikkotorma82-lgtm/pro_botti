
# Optional placeholder — integrate your Capital.com HTTP client here.
# Must implement methods used by live_trader: get_account_summary, get_positions, place_order, close_position.
class CapitalHTTP:
    def __init__(self, api_key: str, username: str, password: str, use_demo: bool=True):
        self.api_key = api_key; self.username=username; self.password=password; self.use_demo=use_demo
    def login(self):
        pass
    def get_account_summary(self):
        return {}
    def get_positions(self):
        return {}
    def place_order(self, symbol: str, side: str, qty: float, price: float):
        pass
    def close_position(self, symbol: str, price: float):
        pass
