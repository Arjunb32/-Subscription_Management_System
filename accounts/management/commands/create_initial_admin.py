from getpass import getpass

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, connection, transaction

from accounts.models import User


class Command(BaseCommand):
    help = "Create the first application admin interactively; no credentials in command arguments."

    def handle(self, *args, **options):
        if User.objects.filter(role=User.Role.ADMIN).exists():
            raise CommandError("An application admin already exists; bootstrap refused.")
        try:
            email = input("Admin email: ").strip()
            password = getpass("Admin password (hidden): ")
            confirmation = getpass("Confirm password (hidden): ")
        except (EOFError, KeyboardInterrupt):
            raise CommandError("Admin creation cancelled.") from None
        if password != confirmation:
            raise CommandError("Passwords do not match.")
        try:
            with transaction.atomic():
                # Serialize concurrent bootstrap commands; no business tables are locked.
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(218936251)")
                if User.objects.filter(role=User.Role.ADMIN).exists():
                    raise CommandError("An application admin already exists; bootstrap refused.")
                user = User.objects.create_user(email, password, role=User.Role.ADMIN)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from None
        except IntegrityError:
            raise CommandError("The account cannot be created; check for an existing email.") from None
        self.stdout.write(self.style.SUCCESS(f"Application admin created (ID {user.pk}). Django admin-site flags remain disabled."))
