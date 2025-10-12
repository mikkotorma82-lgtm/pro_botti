import re, sys, py_compile
from pathlib import Path

P = Path("/root/pro_botti/capital_api.py")
src = P.read_text(encoding="utf-8", errors="replace")
orig = src

# 1) Poista kaikki top-level create_position -funktiot (vas. reunassa)
top_level_pat = re.compile(
    r"(?m)^(def\s+create_position\s*\([^\)]*\)\s*:[\s\S]*?)(?=^\w|\Z)"
)
src = top_level_pat.sub("", src)

# 2) Korvaa luokan sisäinen create_position kokonaan
# Etsitään luokan runko
class_start = re.search(r"(?m)^class\s+CapitalClient\s*:", src)
if not class_start:
    print("❌ CapitalClient-luokkaa ei löytynyt")
    sys.exit(1)

# Etsi luokan sisällä ensimmäinen def create_position
def_pat = re.compile(
    r"(\n[ \t]+)def\s+create_position\s*\([^\)]*\)\s*:[\s\S]*?(?=\n[ \t]+def\s|\nclass\s|\Z)"
)
m = def_pat.search(src, class_start.end())
if not m:
    print("❌ Luokan sisältä ei löytynyt create_position-metodia")
    sys.exit(1)

indent = m.group(1)  # luokan sisäisen metodin sisennys (esim. 4 välilyöntiä)
new_method = f"""
{indent}def create_position(
{indent}    self,
{indent}    direction: str = None,
{indent}    epic_or_symbol: Optional[str] = None,
{indent}    size: Optional[float] = None,
{indent}    currency: Optional[str] = None,
{indent}    **kwargs,
{indent}) -> Dict:
{indent}    \"\"\"
{indent}    Yhtenäistetty create_position:
{indent}    - hyväksyy epic/symbol/epic_or_symbol
{indent}    - sallii extra kwargsit (ei 'unexpected keyword argument')
{indent}    - palauttaa aina dictin
{indent}    \"\"\"
{indent}    # Poimi ja validoi suunta
{indent}    direction = (direction or kwargs.pop("direction", None) or "").upper()
{indent}    if direction not in ("BUY", "SELL"):
{indent}        return {{\"ok\": False, \"error\": \"invalid direction\", \"direction\": direction}}
{indent}
{indent}    # Epic/symbol yhdistäminen
{indent}    epic = kwargs.pop(\"epic\", None)
{indent}    symbol = kwargs.pop(\"symbol\", None)
{indent}    key = epic or symbol or epic_or_symbol or kwargs.get(\"instrument\")
{indent}    if not key:
{indent}        return {{\"ok\": False, \"error\": \"missing epic/symbol\"}}
{indent}
{indent}    epic_resolved = self._resolve_epic(key)
{indent}
{indent}    # koko (size) – käytä annettua tai kwargsista; klampataan spekseillä
{indent}    if size is None:
{indent}        size = kwargs.pop(\"size\", None)
{indent}    try:
{indent}        # clamp_size ottaa 'symbol' avaimena broker_specs.jsoniin – käytetään alkuperäistä key:tä
{indent}        from inspect import signature
{indent}        size = float(size) if size is not None else 1.0
{indent}        size = clamp_size(str(key), size)
{indent}    except Exception:
{indent}        try:
{indent}            size = float(size)
{indent}        except Exception:
{indent}            return {{\"ok\": False, \"error\": \"invalid size\"}}
{indent}
{indent}    # valuutta
{indent}    currency = currency or kwargs.pop(\"currency\", None) or kwargs.pop(\"currencyCode\", None)
{indent}
{indent}    payload = {{\"epic\": epic_resolved, \"direction\": direction, \"size\": size, \"orderType\": \"MARKET\", \"guaranteedStop\": False}}
{indent}    if currency:
{indent}        payload[\"currency\"] = currency
{indent}
{indent}    # salli muut vapaat kentät payloadissa
{indent}    for k, v in list(kwargs.items()):
{indent}        if k not in payload:
{indent}            payload[k] = v
{indent}
{indent}    # Lähetys: käytä sessiota jos _post tai muu raw-funktio puuttuu
{indent}    low = None
{indent}    for name in (\"_create_position\", \"create_position_raw\", \"create_position_inner\", \"_post_position\"):
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
{indent}            url = self._url(\"/api/v1/positions\")
{indent}            r = self.session.post(url, data=json.dumps(payload))
{indent}            if r.status_code // 100 != 2:
{indent}                return {{\"ok\": False, \"status_code\": r.status_code, \"text\": r.text, \"payload\": payload}}
{indent}            try:
{indent}                resp = r.json()
{indent}            except Exception:
{indent}                resp = {{\"dealReference\": None}}
{indent}    except Exception as e:
{indent}        return {{\"ok\": False, \"error\": repr(e), \"payload\": payload, \"raw\": resp}}
{indent}
{indent}    deal_ref = None
{indent}    if isinstance(resp, dict):
{indent}        deal_ref = resp.get(\"dealReference\") or resp.get(\"deal_ref\") or resp.get(\"reference\")
{indent}    return {{\"ok\": True, \"dealReference\": deal_ref, \"payload\": payload, \"raw\": resp}}
"""

src = src[:m.start()] + new_method + src[m.end():]

# 3) Tallenna ja varmista käännös
bak = P.with_suffix(".py.autofix2.bak")
bak.write_text(orig, encoding="utf-8")
P.write_text(src, encoding="utf-8")
try:
    py_compile.compile(str(P), doraise=True)
    print("✅ Päivitetty capital_api.py. Backup:", bak)
except Exception as e:
    print("❌ py_compile epäonnistui:", e)
    sys.exit(1)
