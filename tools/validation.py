from typing import Iterator, Tuple
import numpy as np

def purged_walk_forward(n:int, n_splits:int=5, gap:int=1) -> Iterator[Tuple[np.ndarray,np.ndarray]]:
    """
    Walk-forward ilman vuotoa: jätetään 'gap' train- ja test-joukkojen väliin.
    Palauttaa (train_idx, test_idx) kutakin foldia kohti.
    """
    if n_splits < 1 or n < 10:
        yield np.arange(0, max(1, n-1)), np.arange(max(1, n-1), n)
        return
    fold = n // (n_splits+1)
    for k in range(1, n_splits+1):
        end_tr = fold*k
        tr_end = max(0, end_tr-gap)
        te_end = min(end_tr+fold, n)
        tr_idx = np.arange(0, tr_end)
        te_idx = np.arange(end_tr, te_end)
        if len(tr_idx) and len(te_idx):
            yield tr_idx, te_idx
