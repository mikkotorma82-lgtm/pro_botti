from __future__ import annotations

# Yksinkertainen resolveri. Voit laajentaa/override: /root/pro_botti/state/asset_classes.json
# Palauttaa: 'crypto' | 'index' | 'stock' | 'fx' | 'metal' | 'energy' | 'other'
def resolve_asset_class(symbol: str) -> str:
    s = symbol.upper().strip()

    # Yritä tunnetut indeksit
    index_aliases = ["US SPX 500","US TECH 100","US TECH100","US TECH 100 CASH","US 500","US 100",
                     "GERMANY 40","GER 40","GER40","FRANCE 40","FR 40","EU STOCKS 50","EU 50","UK 100","JAPAN 225"]
    if any(alias in s for alias in index_aliases):
        return "index"

    # Krypto – yleisimmät
    crypto_roots = ["BTC","ETH","XRP","ADA","SOL","DOGE","LTC","BNB","DOT","AVAX"]
    if any(root in s.replace("/","") for root in crypto_roots):
        return "crypto"

    # FX
    fx_pairs = ["EUR/USD","GBP/USD","USD/JPY","USD/CHF","AUD/USD","NZD/USD","USD/CAD","EUR/JPY","GBP/JPY"]
    if any(pair in s for pair in fx_pairs):
        return "fx"

    # Metallit
    metal_aliases = ["XAUUSD","GOLD","XAGUSD","SILVER"]
    if any(m in s.replace("/","") for m in metal_aliases):
        return "metal"

    # Energia
    energy_aliases = ["XTIUSD","WTI","XBRUSD","BRENT","XNGUSD","NATGAS","NAT GAS"]
    if any(e in s.replace("/","") for e in energy_aliases):
        return "energy"

    # Heuristiikka: yksittäinen TICKER ilman välilyöntejä -> osake
    if "/" not in s and " " not in s and s.isalpha() and 1 < len(s) <= 6:
        return "stock"

    return "other"
