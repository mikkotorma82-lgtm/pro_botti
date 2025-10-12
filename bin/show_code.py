import sys
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: python show_code.py <path-to-pyfile>")
    sys.exit(1)

p = Path(sys.argv[1])
if not p.exists():
    print(f"❌ File not found: {p}")
    sys.exit(1)

print(f"\n===== {p} =====\n")
code = p.read_text(encoding="utf-8", errors="replace")
for i, line in enumerate(code.splitlines(), 1):
    print(f"{i:5d}: {line}")
print(f"\n===== END {p} =====\n")
