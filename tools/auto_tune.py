from __future__ import annotations
import numpy as np
from typing import Optional, Tuple, Dict


def _ensure_price(price) -> np.ndarray:
    pr = np.asarray(price, dtype=float).copy()
    # korvaa inf -> nan
    pr[~np.isfinite(pr)] = np.nan
    # ffill
    if np.isnan(pr).any():
        idx = np.arange(len(pr))
        good = ~np.isnan(pr)
        if good.any():
            pr[~good] = np.interp(idx[~good], idx[good], pr[good])
        # jos alku/kaikki puuttuu, korvaa nollalla
        if np.isnan(pr).any():
            pr[np.isnan(pr)] = 0.0
    return pr


def _split_long_short_proba(
    proba: np.ndarray, classes: Optional[np.ndarray]
) -> Tuple[np.ndarray, np.ndarray]:
    """Palauttaa (pl, ps) aina täytettynä."""
    P = np.asarray(proba, dtype=float)
    if P.ndim == 1:
        # Yksi sarake (tod.näk p(class=1)). Tee vastapari.
        pl = P
        ps = 1.0 - pl
        return pl, ps

    if P.shape[1] == 2 and (classes is None):
        # Binääri, muttei class‑nimiä. Oletetaan sarake 1 = long (yleisin sk-learn)
        pl = P[:, 1]
        ps = P[:, 0]
        return pl, ps

    if classes is not None:
        cls = list(classes)

        def find_one(cands):
            for c in cands:
                if c in cls:
                    return cls.index(c)
            return None

        iL = find_one([1, "1", "LONG", "long", "Long"])
        iS = find_one([-1, "-1", "SHORT", "short", "Short"])
        # Jos löytyy vain long, rakenna short vastaparina (jos 2 saraketta) tai pienimmän sarakkeen mukaan
        if iL is not None and iS is not None:
            return P[:, iL], P[:, iS]
        if iL is not None:
            if P.shape[1] == 2:
                other = 1 - iL
                return P[:, iL], P[:, other]
            return P[:, iL], 1.0 - P[:, iL]
        if iS is not None:
            if P.shape[1] == 2:
                other = 1 - iS
                return P[:, other], P[:, iS]
            ps = P[:, iS]
            return 1.0 - ps, ps

    # Fallback: valitse sarake, jonka keskiarvo on suurin = long, pienin = short
    means = np.nanmean(P, axis=0)
    iL = int(np.argmax(means))
    iS = int(np.argmin(means)) if P.shape[1] > 1 else None
    pl = P[:, iL]
    ps = P[:, iS] if iS is not None else (1.0 - pl)
    return pl, ps


def _simulate(
    pl: np.ndarray,
    ps: np.ndarray,
    price: np.ndarray,
    thrL=0.55,
    thrS=0.55,
    sl=0.006,
    tp=0.012,
    gap=0.05,
    prob_decay=0.4,
    commission=1e-4,
) -> Dict[str, float]:
    """
    Yksinkertainen kävelysimulaattori. Varmistetaan ettei tule None‑arvoja.
    """
    pl = np.asarray(pl, dtype=float)
    ps = np.asarray(ps, dtype=float)
    price = _ensure_price(price)

    n = len(price)
    pos = 0  # +1 long, -1 short, 0 flat
    entry = None
    peakL = 0.0
    peakS = 0.0
    pnl = 0.0
    trades = 0
    wins = 0

    for i in range(1, n):
        pL = float(pl[i]) if np.isfinite(pl[i]) else 0.0
        pS = float(ps[i]) if np.isfinite(ps[i]) else 0.0
        pr_now = price[i]
        pr_entry = price[i - 1] if entry is None else entry

        # entry / flip ehdot
        if pos == 0:
            if (pL >= thrL) and (pL - pS >= gap):
                pos = +1
                entry = pr_now
                peakL = pL
                trades += 1
            elif (pS >= thrS) and (pS - pL >= gap):
                pos = -1
                entry = pr_now
                peakS = pS
                trades += 1
        elif pos == +1:
            # huipun päivittys ja decay-exit
            peakL = max(peakL, pL)
            if peakL > 0 and (peakL - pL) / peakL >= prob_decay:
                # exit long
                ret = (pr_now - entry) / entry - commission
                pnl += ret
                wins += int(ret > 0)
                pos = 0
                entry = None
                continue
            # sl/tp
            ret_now = (pr_now - entry) / entry
            if ret_now <= -sl or ret_now >= tp:
                ret = ret_now - commission
                pnl += ret
                wins += int(ret > 0)
                pos = 0
                entry = None
        elif pos == -1:
            peakS = max(peakS, pS)
            if peakS > 0 and (peakS - pS) / peakS >= prob_decay:
                # exit short
                ret = (entry - pr_now) / entry - commission
                pnl += ret
                wins += int(ret > 0)
                pos = 0
                entry = None
                continue
            ret_now = (entry - pr_now) / entry
            if ret_now <= -sl or ret_now >= tp:
                ret = ret_now - commission
                pnl += ret
                wins += int(ret > 0)
                pos = 0
                entry = None

    win_rate = (wins / trades) if trades > 0 else 0.0
    return {"pnl": float(pnl), "trades": int(trades), "win_rate": float(win_rate)}


def grid_search_from_proba(
    proba: np.ndarray, classes: Optional[np.ndarray], price
) -> Dict[str, float]:
    """Käytä kun sinulla on raw predict_proba + classes_."""
    pl, ps = _split_long_short_proba(proba, classes)
    return grid_search(pl, ps, price)


def grid_search(pl: np.ndarray, ps: np.ndarray, price) -> Dict[str, float]:
    """Pieni ruutuhaku turvallisin oletuksin; ei kaadu None/NaN-arvoihin."""
    price = _ensure_price(price)
    pl = np.asarray(pl, dtype=float)
    ps = np.asarray(ps, dtype=float)

    thrs = [0.52, 0.55, 0.6]
    gaps = [0.02, 0.05, 0.08]
    sls = [0.004, 0.006, 0.008]
    tps = [0.008, 0.012, 0.016]
    decs = [0.3, 0.4, 0.5]

    best = None
    best_key = None
    for thrL in thrs:
        for thrS in thrs:
            for g in gaps:
                for sl in sls:
                    for tp in tps:
                        for dc in decs:
                            res = _simulate(pl, ps, price, thrL, thrS, sl, tp, g, dc)
                            score = res[
                                "pnl"
                            ]  # voit laittaa esim. pnl + 0.1*win_rate tms.
                            if (best is None) or (score > best):
                                best = score
                                best_key = (thrL, thrS, g, sl, tp, dc, res)

    if best_key is None:
        # ei yhtään validia simua -> palauta järkevät oletukset
        return {
            "thrL": 0.55,
            "thrS": 0.55,
            "gap": 0.05,
            "sl": 0.006,
            "tp": 0.012,
            "prob_decay": 0.4,
            "win_rate": 0.0,
            "trades": 0,
            "pnl": 0.0,
        }

    thrL, thrS, g, sl, tp, dc, res = best_key
    return {
        "thrL": float(thrL),
        "thrS": float(thrS),
        "gap": float(g),
        "sl": float(sl),
        "tp": float(tp),
        "prob_decay": float(dc),
        "win_rate": float(res["win_rate"]),
        "trades": int(res["trades"]),
        "pnl": float(res["pnl"]),
    }
