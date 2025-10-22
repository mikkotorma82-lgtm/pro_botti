import os
import yaml
import json

class ConfigManager:
    def __init__(self, config_path=None, env_prefix="BOT_", fallback=None):
        self.config_path = config_path
        self.env_prefix = env_prefix
        self.fallback = fallback if fallback else {}
        self.config = {}

        if config_path:
            self.load(config_path)
        else:
            self.config = self.fallback.copy()

    def load(self, path):
        try:
            if path.endswith(".yaml") or path.endswith(".yml"):
                with open(path, "r") as f:
                    self.config = yaml.safe_load(f)
            elif path.endswith(".json"):
                with open(path, "r") as f:
                    self.config = json.load(f)
            else:
                raise ValueError("Unsupported config format")
        except Exception as e:
            print(f"[ConfigManager] load error: {e}")
            self.config = self.fallback.copy()

    def get(self, key, default=None):
        # 1. Ympäristömuuttujat override, 2. config-tiedosto, 3. fallback
        env_key = f"{self.env_prefix}{key}".upper()
        if env_key in os.environ:
            return os.environ[env_key]
        if key in self.config:
            return self.config[key]
        return self.fallback.get(key, default)

    def set(self, key, value):
        self.config[key] = value

    def reload(self):
        if self.config_path:
            self.load(self.config_path)

    def as_dict(self):
        return self.config.copy()
