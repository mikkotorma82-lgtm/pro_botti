#!/usr/bin/env python3
from __future__ import annotations
import os, json, time
from pathlib import Path
from typing import Dict, Any, List

STATE = Path(__file__).resolve().parents[1] / "state"
META_REG = STATE / "models_meta.json"
ADVICE = STATE / "llm_advice.json"

PROMPT = """You are a quantitative trading advisor. You are given cross-validated meta-model metrics per symbol and timeframe (cv_pf_score, entries, asset_class). 
Task:
1) Propose selection rules (thresholds) to maximize out-of-sample PF while keeping enough trades:
   - min_cvpf per asset_class
   - min_entries
   - preferred_tfs (list order)
   - allow_15m (true/false)
   - max_tfs_per_symbol
2) Propose tuner priors (ranges) for triple-barrier (pt_mult, sl_mult, max_hold) per asset_class.
3) Propose time-window blocks (UTC) per asset_class to avoid low-liquidity/spread periods, format HH:MM-HH:MM.
Return strict JSON with keys: selection_rules, tuner_priors, time_blocks, rationale (short).
"""

def load_meta() -> List[Dict[str, Any]]:
    if not META_REG.exists():
        raise SystemExit("models_meta.json missing. Run training first.")
    obj = json.loads(META_REG.read_text() or "{}")
    return obj.get("models", [])

def summarize(rows: List[Dict[str, Any]]) -> str:
    # compact summary for LLM
    lines = []
    for r in rows:
        sym = r["symbol"]; tf = r["tf"]; ac = r.get("asset_class","")
        cv = r.get("cv_pf_score", r.get("auc_purged", 0.0))
        ent = r.get("entries", 0)
        lines.append(f"{sym} | {tf} | {ac} | cvPF={cv:.3f} | entries={ent}")
    return "\n".join(lines[:2000])  # cap

def call_llm(summary: str) -> Dict[str, Any]:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        msg = [
            {"role": "system", "content": "Be precise and conservative. Avoid overfitting; prefer robust rules."},
            {"role": "user", "content": PROMPT + "\n\nDATA:\n" + summary}
        ]
        resp = client.chat.completions.create(model=model, messages=msg, temperature=0.2, max_tokens=int(os.getenv("LLM_MAX_TOKENS","800")))
        txt = resp.choices[0].message.content.strip()
        # Try JSON parsing; if it's not pure JSON, attempt to find JSON block
        try:
            return json.loads(txt)
        except Exception:
            import re
            m = re.search(r"\{.*\}", txt, re.S)
            if m:
                return json.loads(m.group(0))
            raise
    except Exception as e:
        return {"error": str(e)}

def main():
    rows = load_meta()
    summary = summarize(rows)
    advice = call_llm(summary)
    advice_wrapped = {
        "advised_at": int(time.time()),
        "advice": advice
    }
    tmp = ADVICE.with_suffix(".tmp")
    tmp.write_text(json.dumps(advice_wrapped, ensure_ascii=False, indent=2))
    os.replace(tmp, ADVICE)
    print(f"[LLM] wrote {ADVICE}")

if __name__ == "__main__":
    main()
