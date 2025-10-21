import os, logging
from pathlib import Path

def setup_logging(log_name="trader.log"):
    log_dir = Path("/root/pro_botti/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / log_name

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_path),
            logging.StreamHandler()
        ]
    )
    logging.info("Logging initialized: %s", log_path)
