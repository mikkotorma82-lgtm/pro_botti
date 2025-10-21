import os, requests

CAP_BASE = os.getenv("CAPITAL_BASE_URL", os.getenv("CAPITAL_API_BASE", "https://api-capital.backend-capital.com"))
CAP_API_KEY = os.getenv("CAPITAL_API_KEY", "")
CAP_IDENTIFIER = os.getenv("CAPITAL_IDENTIFIER") or os.getenv("CAPITAL_USERNAME", "")
CAP_PASSWORD = os.getenv("CAPITAL_PASSWORD", "")
CAP_ACCOUNT_ID = os.getenv("CAPITAL_ACCOUNT_ID", "")

_session = None
_headers = {
    "X-CAP-API-KEY": CAP_API_KEY,
    "Accept": "application/json",
    "Content-Type": "application/json",
}

def _login_if_needed():
    global _session
    if _session is not None:
        return
    s = requests.Session()
    r = s.post(f"{CAP_BASE}/session", headers=_headers, json={
        "identifier": CAP_IDENTIFIER, "password": CAP_PASSWORD
    })
    r.raise_for_status()
    cst = r.headers.get("CST")
    xst = r.headers.get("X-SECURITY-TOKEN") or r.headers.get("x-security-token")
    if cst: s.headers["CST"] = cst
    if xst: s.headers["X-SECURITY-TOKEN"] = xst
    s.headers.update(_headers)
    _session = s

def get_account_summary():
    _login_if_needed()
    paths = [
        f"{CAP_BASE}/trading/accounts/{CAP_ACCOUNT_ID}",
        f"{CAP_BASE}/trading/accounts",
        f"{CAP_BASE}/accounts/{CAP_ACCOUNT_ID}",
    ]
    last = None
    for p in paths:
        try:
            r = _session.get(p)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            data = r.json()
            acc = {}
            for k in ("equity","balance","margin","available","profitLoss","profit_loss"):
                if k in data: acc[k] = data[k]
            if "available" not in acc:
                for k in ("availableCash","available_to_deal","cashAvailable"):
                    if k in data: acc["available"] = data[k]
            return acc
        except Exception as e:
            last = e
            continue
    if last: raise last
    return {}

def compute_units_from_risk(symbol, entry, stop, pct_risk, pip_value=1.0, min_units=1):
    """units ~= (equity * pct_risk/100) / (abs(entry-stop)*pip_value)"""
    
    try:
        acc = get_account_summary()
    except Exception:
        eq = float(os.getenv("EQUITY0","10000"))
        acc = {"equity": eq, "available": eq}

    equity = float(acc.get("equity") or acc.get("balance") or 0.0)
    risk_cash = equity * float(pct_risk) / 100.0
    dist = abs(float(entry) - float(stop))
    if dist <= 0:
        return int(min_units), acc
    units = int(risk_cash / (dist * float(pip_value)))
    if units < min_units:
        units = int(min_units)
    return units, acc
