from __future__ import annotations
import numpy as np

def apply_cooldown(sig: np.ndarray, n: int) -> np.ndarray:
    if n <= 0: 
        return sig
    out = sig.astype(int).copy()
    last_fire = -10**9
    for i, v in enumerate(out):
        if v != 0:
            if i - last_fire <= n:
                out[i] = 0
            else:
                last_fire = i
    return out

def apply_flip_guard(sig: np.ndarray, n: int) -> np.ndarray:
    if n <= 0:
        return sig
    out = sig.astype(int).copy()
    last_dir = 0
    last_change = -10**9
    for i, v in enumerate(out):
        if v != 0 and last_dir != 0 and v == -last_dir and (i - last_change) <= n:
            out[i] = 0
        elif v != 0 and v != last_dir:
            last_change = i
            last_dir = v
    return out
