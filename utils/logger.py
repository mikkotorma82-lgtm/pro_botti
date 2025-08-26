
from loguru import logger
import sys

def setup_logging(level: str):
    logger.remove()
    logger.add(sys.stdout, level=level)
    return logger
