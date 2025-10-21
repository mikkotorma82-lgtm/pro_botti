#!/usr/bin/env python3
import json
from meta.config import MetaConfig
from meta.training_runner import run_all

def main():
    cfg = MetaConfig()
    summary = run_all(cfg)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
