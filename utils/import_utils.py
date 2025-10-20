import importlib
import sys
import os
from loguru import logger

def dynamic_import(module_name, class_name=None, reload=False, fallback_path=None):
    """
    Dynaaminen import-moduuli, tukee fallback polkuja ja reloadia.
    """
    try:
        if fallback_path and fallback_path not in sys.path:
            sys.path.append(fallback_path)
        module = importlib.import_module(module_name)
        if reload:
            importlib.reload(module)
        if class_name:
            return getattr(module, class_name)
        return module
    except Exception as e:
        logger.error(f"dynamic_import error: {module_name}.{class_name}: {e}")
        return None

def safe_import(module_name, class_name=None, fallback=None):
    """
    Turvallinen import, palauttaa fallback-arvon virheessä.
    """
    try:
        module = importlib.import_module(module_name)
        if class_name:
            return getattr(module, class_name)
        return module
    except Exception as e:
        logger.warning(f"safe_import failed: {module_name}.{class_name}: {e}")
        return fallback

def add_to_sys_path(path):
    """
    Lisää polku sys.pathiin dynaamisesti, ei duplikaatteja.
    """
    path = os.path.abspath(path)
    if path not in sys.path:
        sys.path.append(path)
        logger.info(f"Added to sys.path: {path}")

def reload_module(module):
    """
    Reloadaa annetun moduulin.
    """
    try:
        importlib.reload(module)
        logger.info(f"Reloaded module: {module.__name__}")
    except Exception as e:
        logger.error(f"reload_module error: {e}")
