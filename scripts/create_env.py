"""Create local configuration without printing or overwriting secrets."""
import secrets
from pathlib import Path

root = Path(__file__).resolve().parent.parent
target = root / ".env"
content = (root / ".env.example").read_text(encoding="utf-8")
content = content.replace("DJANGO_SECRET_KEY=\n", f"DJANGO_SECRET_KEY={secrets.token_urlsafe(64)}\n", 1)
try:
    with target.open("x", encoding="utf-8") as stream:
        stream.write(content)
except FileExistsError:
    print("Existing .env preserved.")
else:
    print("Created ignored .env with a generated Django key. Configure DB_* locally before migrating.")
