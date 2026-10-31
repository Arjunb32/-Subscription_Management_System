"""Save local database credentials through a hidden prompt, never command arguments."""
from getpass import getpass
from pathlib import Path

from dotenv import set_key

root = Path(__file__).resolve().parent.parent
target = root / ".env"
if not target.is_file():
    raise SystemExit("Run scripts/create_env.py first.")
try:
    user = input("Database username: ").strip()
    password = getpass("Database password (hidden): ")
except (KeyboardInterrupt, EOFError):
    raise SystemExit("Configuration cancelled; credentials unchanged.") from None
if not user or not password:
    raise SystemExit("Both values are required; credentials unchanged.")
set_key(target, "DB_USER", user)
set_key(target, "DB_PASSWORD", password)
set_key(target, "DB_NAME", "subscription_management")
print("Saved local database settings to the ignored .env. No credentials were printed.")
