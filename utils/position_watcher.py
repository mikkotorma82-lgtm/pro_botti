"""
Position watcher for continuous monitoring of open positions.
Ensures all open positions are managed even if not in active symbol list.
"""
from __future__ import annotations
import time
from typing import Any, Dict, List, Callable, Optional
from loguru import logger


class PositionWatcher:
    """
    Monitors and manages open positions continuously.
    Ensures positions are managed even if symbol is removed from active list.
    """
    
    def __init__(
        self,
        broker: Any,
        check_interval: int = 30,
        guard_config: Optional[Dict] = None
    ):
        """
        Initialize position watcher.
        
        Args:
            broker: Broker instance with methods: open_positions(), close_position()
            check_interval: Seconds between position checks
            guard_config: Configuration for position guard (TP/SL/Trail)
        """
        self.broker = broker
        self.check_interval = check_interval
        self.guard_config = guard_config or {}
        self._running = False
        self._last_check = 0.0
    
    def check_and_manage_positions(self, active_symbols: List[str] | None = None) -> Dict[str, Any]:
        """
        Check all open positions and manage them.
        
        Args:
            active_symbols: List of currently active symbols (for logging only)
        
        Returns:
            Dictionary with check results
        """
        try:
            open_positions = self._get_open_positions()
            
            if not open_positions:
                logger.debug("[PositionWatcher] No open positions")
                return {"open_count": 0, "managed": 0, "errors": 0}
            
            managed = 0
            errors = 0
            inactive_symbols = set()
            
            for pos in open_positions:
                symbol = self._extract_symbol(pos)
                
                # Track which symbols have positions but aren't active
                if active_symbols and symbol not in active_symbols:
                    inactive_symbols.add(symbol)
                
                try:
                    # Apply position management logic
                    self._manage_position(pos)
                    managed += 1
                except Exception as e:
                    logger.error(f"[PositionWatcher] Error managing {symbol}: {e}")
                    errors += 1
            
            if inactive_symbols:
                logger.info(
                    f"[PositionWatcher] Managing {len(inactive_symbols)} positions "
                    f"not in active list: {sorted(inactive_symbols)}"
                )
            
            logger.info(
                f"[PositionWatcher] Checked {len(open_positions)} positions: "
                f"managed={managed}, errors={errors}"
            )
            
            self._last_check = time.time()
            
            return {
                "open_count": len(open_positions),
                "managed": managed,
                "errors": errors,
                "inactive_symbols": list(inactive_symbols),
            }
            
        except Exception as e:
            logger.error(f"[PositionWatcher] Failed to check positions: {e}")
            return {"open_count": 0, "managed": 0, "errors": 1}
    
    def should_check(self) -> bool:
        """Check if enough time has passed since last check."""
        return (time.time() - self._last_check) >= self.check_interval
    
    def _get_open_positions(self) -> List[Dict]:
        """Get open positions from broker."""
        if hasattr(self.broker, "open_positions"):
            return self.broker.open_positions()
        elif hasattr(self.broker, "get_open_positions"):
            return self.broker.get_open_positions()
        else:
            logger.warning("[PositionWatcher] Broker has no open_positions method")
            return []
    
    def _extract_symbol(self, position: Dict) -> str:
        """Extract symbol from position dict."""
        return (
            position.get("symbol") or
            position.get("epic") or
            position.get("instrument") or
            "UNKNOWN"
        )
    
    def _manage_position(self, position: Dict):
        """
        Apply position management logic (TP/SL/Trail).
        This integrates with existing position_guard logic.
        """
        # Import here to avoid circular dependency
        try:
            from position_guard import guard_positions
            
            # Create a mock client wrapper to handle single position
            class SinglePositionBroker:
                def __init__(self, broker, position):
                    self.broker = broker
                    self.position = position
                
                def open_positions(self):
                    return [self.position]
                
                def close_position(self, **kwargs):
                    if hasattr(self.broker, "close_position"):
                        return self.broker.close_position(**kwargs)
                    else:
                        logger.warning("Broker has no close_position method")
            
            mock_broker = SinglePositionBroker(self.broker, position)
            guard_positions(mock_broker, self.guard_config)
            
        except ImportError:
            logger.debug("[PositionWatcher] position_guard not available, skipping guard logic")
        except Exception as e:
            logger.error(f"[PositionWatcher] Error in position management: {e}")
            raise


def create_position_watcher(
    broker: Any,
    check_interval: int = 30,
    guard_config: Optional[Dict] = None
) -> PositionWatcher:
    """Factory function to create PositionWatcher instance."""
    return PositionWatcher(broker, check_interval, guard_config)
