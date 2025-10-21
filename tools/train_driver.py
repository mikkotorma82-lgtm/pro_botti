import importlib, types

def get_trainer_for(sym:str, tf:str):
    import tools.train_core as base
    src = open(base.__file__).read()
    src = src.replace("{{SYM}}", sym).replace("{{TF}}", tf)
    mod = types.ModuleType("train_core_run")
    exec(compile(src, "train_core_run", "exec"), mod.__dict__)
    return mod
