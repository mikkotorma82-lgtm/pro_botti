import json, os, sys

METRICS_NEW = "results/train/metrics.json"
ACTIVE_JSON = "models/active.json"

def load_json(p):
    return json.load(open(p)) if os.path.exists(p) else {}

def main():
    m = load_json(METRICS_NEW)
    if not m:
        print("no_metrics"); return
    active = load_json(ACTIVE_JSON)

    new_score = float(m.get("profit_factor",0) or 0)
    new_model = m.get("model_path","")
    cur_score = float(active.get("profit_factor",0) or 0)

    if new_model and (new_score > cur_score):
        active.update({"model": new_model, "profit_factor": new_score})
        with open(ACTIVE_JSON,"w") as f:
            json.dump(active, f, indent=2)
        print("activated", new_model)
    else:
        print("kept_current")

if __name__ == "__main__":
    main()
