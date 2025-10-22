# meta_agent.py
import random, json, os
from datetime import datetime

AGENTS=["Trend","MeanReversion","Breakout","Range","RL"]

def select_agent(scores):
    best = max(scores,key=scores.get)
    decision={"timestamp":datetime.utcnow().isoformat(),
              "winner":best,"scores":scores}
    os.makedirs("data",exist_ok=True)
    json.dump(decision,open("data/meta_decision.json","w"),indent=2)
    print("[META_AGENT] Winner:",best)
    return best
