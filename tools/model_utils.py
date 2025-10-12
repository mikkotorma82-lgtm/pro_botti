import json, os

def meta_path(sym:str, tf:str): 
    os.makedirs("models/meta", exist_ok=True)
    return f"models/meta/{sym}_{tf}.json"

def load_meta(sym:str, tf:str):
    p = meta_path(sym, tf)
    if os.path.exists(p):
        with open(p,"r") as f: 
            try: return json.load(f)
            except: return {}
    return {}

def save_meta(sym:str, tf:str, auc:float, n:int, extra:dict=None):
    m = {"auc":float(auc), "n":int(n)}
    if extra: m.update(extra)
    with open(meta_path(sym,tf),"w") as f: json.dump(m,f)

def should_accept(sym:str, tf:str, new_auc:float, min_auc:float, bp_improve:float):
    old = load_meta(sym, tf)
    old_auc = float(old.get("auc", 0.0))
    # vaaditaan joko min_auc tai pienen pieni parannus per basis point
    accept = new_auc >= max(min_auc, old_auc + bp_improve/10000.0)
    return accept, old_auc
