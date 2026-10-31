from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import AttemptBucket


class Command(BaseCommand):
    help = "Remove expired authentication attempt counters (safe to run daily)."

    def handle(self, *args, **options):
        count, _ = AttemptBucket.objects.filter(expires_at__lte=timezone.now()).delete()
        self.stdout.write(f"Removed {count} expired counter(s).")
