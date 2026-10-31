from django.core.management.base import BaseCommand, CommandError
from django.db import connection, OperationalError
from django.db.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = "Read-only database connectivity, existing tables, and migration compatibility checks."

    def handle(self, *args, **options):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database()")
                name = cursor.fetchone()[0]
                tables = set(connection.introspection.table_names(cursor))
            self.stdout.write(f"Connected to {name}; {len(tables)} public tables.")
            if "auth_user" in tables:
                raise CommandError("Existing auth_user table detected. Assess custom-user compatibility before migrating; do not reset or fake migrations.")
            executor = MigrationExecutor(connection)
            executor.loader.check_consistent_history(connection)
            applied = executor.loader.applied_migrations
            if "accounts_user" in tables and ("accounts", "0001_initial") not in applied:
                raise CommandError("accounts_user exists without the matching migration history. Review schema compatibility.")
            if any(app in {"auth", "sessions"} for app, _ in applied) and ("accounts", "0001_initial") not in applied:
                raise CommandError("Django authentication migrations already exist without this user model. Assess compatibility first.")
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
            self.stdout.write(self.style.SUCCESS(f"Migration history is consistent; {len(plan)} pending migration(s)."))
        except CommandError:
            raise
        except OperationalError as exc:
            # Classify without exposing the connection string, username or password.
            error = str(exc).lower()
            if "no password supplied" in error:
                reason = "DB_PASSWORD is empty or was not read from the local environment."
            elif "password authentication failed" in error:
                reason = "PostgreSQL rejected the configured credentials. Verify DB_USER and DB_PASSWORD locally."
            elif "does not exist" in error:
                reason = "The configured database or database role does not exist. Verify local DB_NAME and DB_USER."
            elif "permission denied" in error:
                reason = "The database role lacks access. Ask the database owner to review privileges."
            else:
                reason = "Check DB_HOST, DB_PORT, PostgreSQL readiness and local access configuration."
            raise CommandError(f"Database connection failed. {reason} Credentials are never printed.") from None
        except Exception:
            raise CommandError("Database diagnostic failed. Check local DB_* settings and server access; credentials are never printed.") from None
