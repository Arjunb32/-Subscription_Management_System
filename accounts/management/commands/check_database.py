from django.core.management.base import BaseCommand, CommandError
from django.db import connection
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
        except Exception:
            raise CommandError("Database diagnostic failed. Check local DB_* settings and server access; credentials are never printed.") from None
