#!/usr/bin/env python3
import json, math
from pathlib import Path

def load_specs():
    try:
        d = json.load(open("data/broker_specs.json"))
        return {r["symbol"]: r for r in d if "error" not in r}
    except Exception:
        return {}

def clamp(symbol, qty):
    s = load_specs().get(symbol) or {}
    mn = float(s.get("min_size", 0) or 0)
    st = float(s.get("step", 1) or 1)
    if mn and qty < mn: qty = mn
    if st: qty = round(qty/st)*st
    return max(qty, mn)

def size_by_margin(symbol, price, free_margin, max_leverage, risk_frac=0.01):
    # käytä vain osa vapaasta marginaalista
    alloc = max(free_margin * float(risk_frac), 0.0)
    if alloc <= 0 or price <= 0 or max_leverage <= 0:
        return clamp(symbol, 0.0)
    # CFD: tarvittava marginaali ≈ (position_value / leverage)
    # position_value = size * price
    # => size_max = alloc * leverage / price
    raw = (alloc * float(max_leverage)) / float(price)
    return clamp(symbol, raw)
