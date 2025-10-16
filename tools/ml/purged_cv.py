from __future__ import annotations
from typing import Iterator, Tuple
import numpy as np

class PurgedTimeSeriesSplit:
    """
    Aikasarjajako ilman vuotoa:
    - Kasvava time-ordered train -> test
    - Embargo: poistaa trainin lopusta N havaintoa, jotta testiin vuotava tieto estyy
    """
    def __init__(self, n_splits: int = 5, embargo: int = 0):
        assert n_splits >= 2
        self.n_splits = int(n_splits)
        self.embargo = int(max(0, embargo))

    def split(self, X) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
        n = len(X)
        fold = max(1, n // (self.n_splits + 1))
        for i in range(self.n_splits):
            train_end = (i + 1) * fold
            test_end = min((i + 2) * fold, n)
            test_idx = np.arange(train_end, test_end)
            embargo_lo = max(0, train_end - self.embargo)
            train_idx = np.arange(0, embargo_lo)
            yield train_idx, test_idx
