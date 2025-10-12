import csv, json, os

CSV_FILE = "/root/pro_botti/data/capital_symbols_checked.csv"
OUT_FILE = "/root/pro_botti/data/instrument_map.json"

symbols = {}

with open(CSV_FILE, newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        sym = row["symbol"]
        symbols[sym] = {
            "epic": row["epic"],
            "displayName": row["name"],
            "min_trade_size": float(row["minDealSize"]) if row["minDealSize"] != "-" else None,
            "margin_factor": float(row["marginFactor"]) if row["marginFactor"] != "-" else None,
            "leverage": float(row["leverage"]) if row["leverage"] != "-" else None,
        }

with open(OUT_FILE, "w", encoding="utf-8") as f:
    json.dump(symbols, f, indent=2)

print(f"✅ Instrument map tallennettu: {OUT_FILE}")
