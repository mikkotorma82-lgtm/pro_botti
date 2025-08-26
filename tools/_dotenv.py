from __future__ import annotations
import os
from pathlib import Path


def _parse_line(line: str):
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    if s.startswith("export "):
        s = s[7:].lstrip()
    if "=" not in s:
        return None
    k, v = s.split("=", 1)
    k = k.strip()
    v = v.strip()
    if v and v[0] not in ("'", '"') and "#" in v:
        v = v.split("#", 1)[0].rstrip()
    if (v.startswith('"') and v.endswith('"')) or (
        v.startswith("'") and v.endswith("'")
    ):
        v = v[1:-1]
    return k, v


def _load_one(p: Path, overwrite: bool) -> int:
    if not p.exists():
        return 0
    n = 0
    for raw in p.read_text().splitlines():
        kv = _parse_line(raw)
        if not kv:
            continue
        k, v = kv
        if overwrite or k not in os.environ:
            os.environ[k] = v
            n += 1
    return n


def load_dotenv(path: str | Path | None = None, overwrite: bool = False) -> int:
    root = Path(__file__).resolve().parents[1]
    if path:
        return _load_one(Path(path), overwrite)
    cnt = 0
    for name in ("botti.env", ".env"):
        cnt += _load_one(root / name, overwrite)
    return cnt
