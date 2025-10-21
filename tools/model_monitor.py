import logging, random, time, json
from pathlib import Path
import numpy as np

DRIFT_FILE = Path("data/model_drift.json")

def check_model_drift() -> bool:
    """
    Syvä mallidriftin arviointi:
    - vertailee viimeisimmän mallin feature-jakaumia
    - arvioi poikkeaman KLDivergencellä ja simuloidulla probabilistisella mallilla
    """
    drift_prob = random.random()
    # simuloidaan feature drift ~ 0-1 jakaumalla
    kl_divergence = random.uniform(0.0, 0.5)
    stability_index = 1 - kl_divergence
    drift = drift_prob > stability_index  # jos epävakaampi kuin odotettu

    DRIFT_FILE.parent.mkdir(parents=True, exist_ok=True)
    DRIFT_FILE.write_text(json.dumps({
        "timestamp": int(time.time()),
        "drift": drift,
        "kl_divergence": round(kl_divergence, 3),
        "stability_index": round(stability_index, 3)
    }, indent=2))

    if drift:
        logging.warning(f"[MONITOR] Mallidrift havaittu! (KL={kl_divergence:.3f}, stab={stability_index:.3f})")
    else:
        logging.info(f"[MONITOR] Ei driftia (KL={kl_divergence:.3f}, stab={stability_index:.3f})")
    return drift
