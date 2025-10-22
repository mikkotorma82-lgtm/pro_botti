import re, sys, py_compile
from pathlib import Path

P = Path("/root/pro_botti/capital_api.py")
src = P.read_text(encoding="utf-8", errors="replace")
orig = src

# 1) Poista kaikki TOP-LEVEL create_position()-funktiot (ei sisennystä rivin alussa)
src = re.sub(
    r"(?ms)^(def\s+create_position\s*\([^)]*\)\s*:[\s\S]*?)(?=^[^\s]|\Z)",
    "",
    src
)

# 2) Etsi CapitalClient-luokka
m_class = re.search(r"(?m)^class\s+CapitalClient\s*:", src)
if not m_class:
    print("❌ CapitalClient-luokkaa ei löydy")
    sys.exit(1)

# 3) Etsi luokan SISÄLTÄ create_position-metodi; jos ei löydy, lisätään luokkaan
#    Huom: sallitaan kommentteja/metodikopioita; otetaan ENSIMMÄINEN match luokan jälkeen
def_pat = re.compile(r"(?s)(\n[ \t]+)def\s+create_position\s*\([^)]*\)\s*:[\s\S]*?(?=\n[ \t]+def\s|\nclass\s|\Z)")
m_def = def_pat.search(src, m_class.end())

indent = "    "  # 4 välilyöntiä (luokan sisällä)
new_method = f"""
{indent}def create_position(
{indent}    self,
{indent}    direction: str = None,
{indent}    epic_or_symbol: str | None = None,
{indent}    size: float | None = None,
{indent}    currency: str | None = None,
{indent}    **kwargs,
{indent}) -> Dict:
{indent}    \"\"\"
{indent}    Yhtenäistetty create_position:
{indent}      - hyväksyy epic/symbol/epic_or_symbol
{indent}      - sallii extra kwargsit
{indent}      - palauttaa AINA dictin eikä nosta TypeErroria turhasta
{indent}    \"\"\"
{indent}    # suunta
{indent}    direction = (direction or kwargs.pop("direction", None) or "").upper()
{indent}    if direction not in ("BUY", "SELL"):
{indent}        return {{ "ok": False, "error": "invalid direction", "direction": direction }}
{indent}
{indent}    # epic/symbol
{indent}    epic  = kwargs.pop("epic", None)
{indent}    symbol = kwargs.pop("symbol", None)
{indent}    key = epic or symbol or epic_or_symbol or kwargs.get("instrument")
{indent}    if not key:
{indent}        return {{ "ok": False, "error": "missing epic/symbol" }}
{indent}
{indent}    epic_resolved = self._resolve_epic(key)
{indent}
{indent}    # size (klampataan broker_specs.jsonin mukaan jos löytyy)
{indent}    if size is None:
{indent}        size = kwargs.pop("size", None)
{indent}    try:
{indent}        size = float(size) if size is not None else 1.0
{indent}    except Exception:
{indent}        return {{ "ok": False, "error": "invalid size" }}
{indent}
{indent}    try:
{indent}        size = clamp_size(str(key), size)
{indent}    except Exception:
{indent}        pass
{indent}
{indent}    currency = currency or kwargs.pop("currency", None) or kwargs.pop("currencyCode", None)
{indent}
{indent}    payload = {{
{indent}        "epic": epic_resolved,
{indent}        "direction": direction,
{indent}        "size": size,
{indent}        "orderType": "MARKET",
{indent}        "guaranteedStop": False,
{indent}    }}
{indent}    if currency:
{indent}        payload["currency"] = currency
{indent}    # salli muut vapaat kentät
{indent}    for k, v in list(kwargs.items()):
{indent}        if k not in payload:
{indent}            payload[k] = v
{indent}
{indent}    # kutsu mahdollisia alempia toteutuksia
{indent}    low = None
{indent}    for name in ("_create_position","create_position_raw","create_position_inner","_post_position"):
{indent}        low = getattr(self, name, None)
{indent}        if callable(low):
{indent}            break
{indent}
{indent}    resp = None
{indent}    try:
{indent}        if callable(low):
{indent}            try:
{indent}                resp = low(payload)
{indent}            except TypeError:
{indent}                resp = low(**payload)
{indent}        else:
{indent}            # suora API-kutsu
{indent}            url = self._url("/api/v1/positions")
{indent}            r = self.session.post(url, data=json.dumps(payload))
{indent}            if r.status_code // 100 != 2:
{indent}                return {{ "ok": False, "status_code": r.status_code, "text": r.text, "payload": payload }}
{indent}            try:
{indent}                resp = r.json()
{indent}            except Exception:
{indent}                resp = {{}}
{indent}    except Exception as e:
{indent}        return {{ "ok": False, "error": repr(e), "payload": payload, "raw": resp }}
{indent}
{indent}    deal_ref = resp.get("dealReference") if isinstance(resp, dict) else None
{indent}    return {{ "ok": True, "dealReference": deal_ref, "payload": payload, "raw": resp }}
"""

if m_def:
    # korvaa olemassa oleva metodi
    start, end = m_def.span()
    src = src[:start] + "\n" + new_method.strip("\n") + "\n" + src[end:]
else:
    # lisää luokan alkuun heti __init__in jälkeen (tai luokan alkuun)
    # etsi kohta, jossa ensimmäinen luokan sisäinen def alkaa
    m_first_def = re.search(r"(?m)^\s+def\s+\w+\s*\(", src[m_class.end():])
    insert_at = m_class.end() + (m_first_def.start() if m_first_def else 0)
    src = src[:insert_at] + "\n" + new_method.strip("\n") + "\n" + src[insert_at:]

# 4) Tallenna ja kompailaa
bak = P.with_suffix(".py.backup_before_clean")
bak.write_text(orig, encoding="utf-8")
P.write_text(src, encoding="utf-8")

try:
    py_compile.compile(str(P), doraise=True)
    print("✅ capital_api.py korjattu. Backup:", bak)
except Exception as e:
    print("❌ py_compile epäonnistui:", e)
    sys.exit(1)
