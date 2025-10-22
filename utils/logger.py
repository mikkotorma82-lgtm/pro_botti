import logging
import sys

def setup_logger(name="bot", log_level=logging.INFO, log_file=None):
    """
    Luo loggerin, joka kirjoittaa sekä konsoliin että tarvittaessa tiedostoon.
    """
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s %(name)s: %(message)s')

    # Konsoliloki
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(log_level)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # Tiedostoloki
    if log_file:
        fh = logging.FileHandler(log_file)
        fh.setLevel(log_level)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger

# Globaalikäyttö
global_logger = setup_logger()

def info(msg):
    global_logger.info(msg)

def debug(msg):
    global_logger.debug(msg)

def error(msg):
    global_logger.error(msg)

def warning(msg):
    global_logger.warning(msg)
