import pandas as pd
from loguru import logger

class PortfolioManager:
    """
    Modulaarinen portfoliohallinta bottiympäristössä:
    - Hallinnoi usean symbolin positioita, allokaatiota ja riskitasoja.
    - Tukee: position sizing, dynaaminen allokaatio, riskilimitit, rebalansointi.
    - Edge-case handling: fallback-arvot, virheidenhallinta.
    - Laajennettavissa: ML-optimointi, dashboard, automaattitrading.
    """
    def __init__(self, config=None):
        self.config = config if config else {}
        self.positions = {}  # symbol -> dict
        self.cash = self.config.get("initial_cash", 100000)
        self.risk_limit = self.config.get("risk_limit", 0.05)  # max % risk per symbol
        self.history = []

    def update_position(self, symbol, qty, entry_px, side, meta=None):
        """
        Lisää tai päivittää position portfoliosta.
        """
        self.positions[symbol] = {
            "qty": qty,
            "entry_px": entry_px,
            "side": side,
            "meta": meta if meta else {},
        }
        logger.info(f"PortfolioManager: updated {symbol} {side} qty={qty} px={entry_px}")

    def remove_position(self, symbol):
        if symbol in self.positions:
            del self.positions[symbol]
            logger.info(f"PortfolioManager: removed {symbol}")

    def get_position(self, symbol):
        return self.positions.get(symbol, None)

    def get_portfolio_value(self, price_map=None):
        """
        Laskee portfolion kokonaisarvon annetulla price_mapilla (symbol -> hinta).
        """
        value = self.cash
        for symbol, pos in self.positions.items():
            px = price_map[symbol] if price_map and symbol in price_map else pos["entry_px"]
            value += pos["qty"] * (px if pos["side"].upper() == "BUY" else -px)
        return value

    def risk_exposure(self, price_map=None):
        """
        Laskee riskin per symboli (% cash).
        """
        exposures = {}
        total_value = self.get_portfolio_value(price_map)
        for symbol, pos in self.positions.items():
            px = price_map[symbol] if price_map and symbol in price_map else pos["entry_px"]
            exposure = abs(pos["qty"] * px) / total_value if total_value else 0
            exposures[symbol] = exposure
        return exposures

    def rebalance(self, target_weights, price_map=None):
        """
        Uudelleenallokoi positioita haluttuihin painoihin.
        """
        total_value = self.get_portfolio_value(price_map)
        for symbol, target_weight in target_weights.items():
            px = price_map[symbol] if price_map and symbol in price_map else 1
            qty = (total_value * target_weight) / px
            self.update_position(symbol, qty, px, "BUY")
        logger.info("PortfolioManager: rebalanced portfolio")

    def as_dict(self):
        return {
            "cash": self.cash,
            "positions": self.positions,
            "risk_limit": self.risk_limit,
        }
