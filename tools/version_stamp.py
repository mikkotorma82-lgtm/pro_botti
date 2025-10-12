import time, logging
VERSION = time.strftime("%Y%m%d-%H%M")
def log_startup(modname=None):
    lg = logging.getLogger(modname or __name__)
    try:
        lg.info("start", extra={"version": VERSION})
    except Exception:
        lg.info(f"start version={VERSION}")
