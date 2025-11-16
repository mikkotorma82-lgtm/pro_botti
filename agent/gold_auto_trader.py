"""
Automated Gold Trader for Capital.com.
"""

import logging
from typing import Optional, Dict
from tools.capital_client import CapitalClient
from tools.capital_constants import get_display_symbol

logger = logging.getLogger(__name__)


class GoldAutoTrader:
    """
    Automated trading system for gold on Capital.com.
    
    This class manages the full lifecycle of gold trading including:
    - Data fetching and feature engineering
    - Signal generation from trained models
    - Order execution and position management
    - Risk management and stop-loss/take-profit
    """
    
    def __init__(
        self,
        client: CapitalClient,
        symbol: str = "XAUUSD",
        timeframe: str = "15m",
        model_path: Optional[str] = None,
        risk_pct: float = 0.02,
        stop_loss_atr: float = 2.0,
        take_profit_atr: float = 4.0,
    ):
        """
        Initialize the GoldAutoTrader.
        
        Args:
            client: Capital.com API client
            symbol: Trading symbol (e.g., "XAUUSD")
            timeframe: Trading timeframe (e.g., "15m", "1h")
            model_path: Path to trained model file
            risk_pct: Risk per trade as percentage of capital
            stop_loss_atr: Stop loss in ATR multiples
            take_profit_atr: Take profit in ATR multiples
        """
        self.client = client
        self.logical_symbol = symbol  # Internal symbol for API calls
        self.display_symbol = get_display_symbol(symbol)  # User-facing symbol
        self.timeframe = timeframe
        self.model_path = model_path
        self.risk_pct = risk_pct
        self.stop_loss_atr = stop_loss_atr
        self.take_profit_atr = take_profit_atr
        self.model = None
        self.is_running = False
        
        self._print_header()
    
    def _print_header(self):
        """Print initialization header with configuration."""
        logger.info("=" * 60)
        logger.info("AUTOMATED GOLD TRADER INITIALIZED")
        logger.info("=" * 60)
        logger.info("Symbol: %s", self.display_symbol)
        logger.info("Timeframe: %s", self.timeframe)
        logger.info("Risk per trade: %.2f%%", self.risk_pct * 100)
        logger.info("Stop Loss: %.1fx ATR", self.stop_loss_atr)
        logger.info("Take Profit: %.1fx ATR", self.take_profit_atr)
        if self.model_path:
            logger.info("Model: %s", self.model_path)
        logger.info("=" * 60)
    
    def load_model(self, model_path: Optional[str] = None):
        """
        Load trained model from file.
        
        Args:
            model_path: Path to model file (overrides constructor value)
        """
        import joblib
        
        path = model_path or self.model_path
        if not path:
            raise ValueError("No model path provided")
        
        try:
            self.model = joblib.load(path)
            logger.info("Model loaded successfully from %s", path)
        except Exception as e:
            logger.error("Failed to load model from %s: %s", path, e)
            raise
    
    def start(self):
        """Start the automated trading loop."""
        if not self.model:
            logger.warning("No model loaded. Call load_model() first.")
            return
        
        self.is_running = True
        logger.info("Starting automated trading for %s on %s timeframe",
                   self.display_symbol, self.timeframe)
        
        # Main trading loop would go here
        # This is a stub - actual implementation would include:
        # - Fetch latest data
        # - Generate features
        # - Get model prediction
        # - Execute trades based on signals
        # - Manage positions
    
    def stop(self):
        """Stop the automated trading loop."""
        self.is_running = False
        logger.info("Stopping automated trading for %s", self.display_symbol)
    
    def get_status(self) -> Dict:
        """
        Get current trader status.
        
        Returns:
            Dictionary with trader status information
        """
        return {
            "symbol": self.display_symbol,
            "logical_symbol": self.logical_symbol,
            "timeframe": self.timeframe,
            "is_running": self.is_running,
            "model_loaded": self.model is not None,
        }
