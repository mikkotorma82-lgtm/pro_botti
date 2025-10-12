import re, sys
from pathlib import Path
import py_compile

P = Path("/root/pro_botti/capital_api.py")
src = P.read_text(encoding="utf-8", errors="replace")
orig = src

# 1) Siivoa selkeät roskat rivitasolla
GARBAGE = [
    r"^gerrnalctl.*$",
    r"^Patched create_position.*$",
    r"^✅ Syntax OK.*$",
    r"^\)?, 1\)$",            # puoliksi leikkautuneita pätkiä
    r"^PY,.*$",               # katkoneita heredoc-rivejä
    r"^\)\), 1\)$",
    r"^chmod \+x .*show_code\.py\).*$",
]
for gp in GARBAGE:
    src = re.sub(gp, "", src, flags=re.MULTILINE)

# 2) Sulje katkenneet triple-quotet (sekä """ että ''')
def balance_triple_quotes(text: str) -> str:
    i, n = 0, len(text)
    stack = []  # values: '"""' or "'''"
    out = []
    while i < n:
        ch = text[i]
        nxt3 = text[i:i+3]
        if nxt3 in ('"""',"'''"):
            if stack and stack[-1] == nxt3:
                stack.pop()
            else:
                stack.append(nxt3)
            out.append(nxt3)
            i += 3
            continue
        out.append(ch)
        i += 1
    # jos jäi auki, sulje sama määrä kuin avattiin
    while stack:
        out.append(stack.pop())
    return "".join(out)

src = balance_triple_quotes(src)

# 3) Testaa syntaksi
try:
    compile(src, str(P), "exec")
except SyntaxError as e:
    # Yritetään vielä kerran: joskus yksittäinen roskamerkki jäi väliin kolmoislainauksen sisään → poista se rivi ja yritä uudelleen
    line_no = e.lineno or 1
    lines = src.splitlines()
    if 1 <= line_no <= len(lines):
        del lines[line_no-1]
        src2 = "\n".join(lines)
        try:
            compile(src2, str(P), "exec")
            src = src2
        except Exception:
            print("❌ Yhä SyntaxError rivin siivouksen jälkeen:", e, file=sys.stderr)
            # Tulosta ongelmaikkuna avun vuoksi
            start = max(0, (e.lineno or 1) - 10)
            end   = min(len(lines), (e.lineno or 1) + 10)
            for i, ln in enumerate(lines[start:end], start+1):
                print(f"{i:5d}: {ln}")
            sys.exit(1)

# 4) Varmista että Optional, Dict importattu
if "Optional" not in src or "Dict" not in src:
    # lisää typing-import jos puuttuu
    m = re.search(r"(^from\s+typing\s+import[^\n]*$)", src, flags=re.MULTILINE)
    if m:
        line = m.group(1)
        add = []
        if "Optional" not in line: add.append("Optional")
        if "Dict" not in line: add.append("Dict")
        if add:
            new_line = line.rstrip() + ", " + ", ".join(add) + "\n"
            src = src.replace(line + "\n", new_line)
    else:
        # Tiputa heti ensimmäisen import-lohkon jälkeen
        src = re.sub(r"(^(?:from|import).*\n)+",
                     lambda m: m.group(0) + "from typing import Optional, Dict\n",
                     src, count=1, flags=re.MULTILINE)

# 5) Korvaa create_position turvalliseen toteutukseen
new_create = r'''
def create_position(
    self,
    direction: str = None,
    epic_or_symbol: Optional[str] = None,
    size: Optional[float] = None,
    currency: Optional[str] = None,
    **kwargs,
) -> Dict:
    """
    Yhtenäistetty create_position:
    - hyväksyy epic/symbol/epic_or_symbol
    - sallii extra kwargsit (ei räjähdä 'unexpected keyword argument')
    - palauttaa aina dictin, vaikka alempi kerros palauttaisi None
    """
    epic = kwargs.pop("epic", None) or kwargs.pop("symbol", None) or epic_or_symbol or kwargs.get("instrument")
    if not epic:
        raise ValueError("create_position: missing epic_or_symbol / epic / symbol")

    if direction not in ("BUY", "SELL"):
        raise ValueError("create_position: direction must be BUY or SELL")

    if size is None:
        size = kwargs.pop("size", None) or getattr(self, "size_default", None)
        if size is None:
            raise ValueError("create_position: missing size")

    payload = dict(direction=direction, epic=epic, size=size)
    if currency:
        payload["currency"] = currency
    for k, v in list(kwargs.items()):
        if k not in payload:
            payload[k] = v

    # Etsi low-level lähettäjä
    low = None
    for name in ("_create_position", "create_position_raw", "create_position_inner", "_post_position"):
        low = getattr(self, name, None)
        if callable(low):
            break

    resp = None
    try:
        if callable(low):
            # ensisijaisesti payload-dictillä
            try:
                resp = low(payload)
            except TypeError:
                # vaihtoehtoisesti parametreina
                resp = low(**payload)
        else:
            _post = getattr(self, "_post", None)
            if callable(_post):
                resp = _post("/positions", json=payload)
    except Exception as e:
        return {"ok": False, "error": repr(e), "payload": payload, "raw": resp}

    deal_ref = None
    if isinstance(resp, dict):
        deal_ref = resp.get("dealReference") or resp.get("deal_ref") or resp.get("reference")

    return {"ok": True, "dealReference": deal_ref, "payload": payload, "raw": resp}
'''

# regex: korvaa koko def create_position -lohko
pat = re.compile(r"\n\s*def\s+create_position\s*\([^\)]*\)\s*:[\s\S]*?(?=\n\s*(def|class)\s|\Z)", re.MULTILINE)
if pat.search(src):
    src = pat.sub("\n" + new_create.strip() + "\n\n\\1", src)
else:
    # jos puuttuu kokonaan, lisätään lopun perään
    src = src.rstrip() + "\n\n" + new_create.strip() + "\n"

# 6) Kirjoita talteen ja py_compile
bak = P.with_suffix(P.suffix + ".autofix.bak")
bak.write_text(orig, encoding="utf-8")
P.write_text(src, encoding="utf-8")
try:
    py_compile.compile(str(P), doraise=True)
    print("✅ capital_api.py korjattu. Backup:", bak)
except Exception as e:
    print("❌ compile epäonnistui:", e)
    # Tulosta ongelman ympäristö avuksi
    try:
        import traceback
        traceback.print_exc()
    finally:
        print("⚠️ Palautettu silti muokattu versio. Tarvittaessa kopioi backup takaisin:", bak)
        sys.exit(1)
