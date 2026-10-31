"""Optional isolated local PostgreSQL server; never connects to the working server.

Usage: python scripts/test_postgres.py start|stop|run <Django arguments>
Requires PostgreSQL binaries and the project's installed dependencies.
"""
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / ".local" / "auth-test-postgres"
DATA = LOCAL / "data"
CREDENTIALS = LOCAL / "connection.json"
PORT = 7130


def binary(name):
    found = shutil.which(name)
    if found:
        return found
    folder = Path(os.environ.get("PG_BIN", r"C:\Program Files\PostgreSQL\18\bin"))
    candidate = folder / (name + (".exe" if os.name == "nt" else ""))
    if not candidate.is_file():
        raise SystemExit("Set PG_BIN to your PostgreSQL bin directory.")
    return str(candidate)


def invoke(args, **kwargs):
    if os.name == "nt":
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        kwargs["startupinfo"] = startup
    return subprocess.run(args, check=True, cwd=ROOT, **kwargs)


def start():
    LOCAL.mkdir(parents=True, exist_ok=True)
    if not CREDENTIALS.exists():
        if DATA.exists():
            raise SystemExit("Unrecognized existing test data directory; refusing to overwrite it.")
        settings = {"host": "127.0.0.1", "port": PORT, "user": "auth_test", "password": secrets.token_urlsafe(32)}
        with CREDENTIALS.open("x", encoding="utf-8") as stream:
            json.dump(settings, stream)
    settings = json.loads(CREDENTIALS.read_text(encoding="utf-8"))
    if not (DATA / "PG_VERSION").exists():
        password_file = LOCAL / "init-password"
        try:
            password_file.write_text(settings["password"], encoding="utf-8")
            invoke([binary("initdb"), "-D", str(DATA), "-U", "auth_test",
                    "--auth=scram-sha-256", "--pwfile", str(password_file), "--encoding=UTF8", "--no-locale"])
        finally:
            password_file.unlink(missing_ok=True)
    status = subprocess.run([binary("pg_ctl"), "-D", str(DATA), "status"], capture_output=True)
    if status.returncode != 0:
        invoke([binary("pg_ctl"), "-D", str(DATA), "-l", str(LOCAL / "server.log"),
                "-o", f"-h 127.0.0.1 -p {PORT}", "-w", "start"])
    import psycopg
    from psycopg import sql
    with psycopg.connect(dbname="postgres", **settings, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", ("test_subscription_management",)).fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier("test_subscription_management")))
    print(f"Isolated test PostgreSQL ready on 127.0.0.1:{PORT}; working database untouched.")


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action == "start":
        start()
    elif action == "stop":
        if not (DATA / "postmaster.pid").exists():
            print("Isolated test server is already stopped.")
            return
        invoke([binary("pg_ctl"), "-D", str(DATA), "-m", "fast", "-w", "stop"])
    elif action == "run" and len(sys.argv) > 2:
        settings = json.loads(CREDENTIALS.read_text(encoding="utf-8"))
        environment = os.environ.copy()
        environment.update({
            "DJANGO_SETTINGS_MODULE": "config.test_settings",
            "TEST_DB_NAME": "test_subscription_management",
            "TEST_DB_HOST": settings["host"], "TEST_DB_PORT": str(settings["port"]),
            "TEST_DB_USER": settings["user"], "TEST_DB_PASSWORD": settings["password"],
        })
        invoke([sys.executable, "manage.py", *sys.argv[2:]], env=environment)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
