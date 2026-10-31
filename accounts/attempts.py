"""Atomic shared rate limits; do not trust arbitrary forwarded IP headers."""
from datetime import datetime, timezone as datetime_timezone

from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from rest_framework.exceptions import Throttled

from .models import AttemptBucket


def limit_attempts(scope, identities_and_limits):
    """Consume one attempt for each (identity, limit, window_seconds) rule.

    Fixed windows are anchored in UTC. Lock keys in stable order so concurrent
    workers serialize increments without deadlocks or process-local caches.
    """
    now = timezone.now().timestamp()
    rules = []
    for identity, limit, seconds in identities_and_limits:
        window = int(now) // seconds
        key = salted_hmac("auth-attempt", f"{scope}:{identity}:{seconds}:{window}", algorithm="sha256").hexdigest()
        end = datetime.fromtimestamp((window + 1) * seconds, tz=datetime_timezone.utc)
        rules.append((key, limit, end))
    wait = 0
    with transaction.atomic():
        buckets = []
        for key, maximum, end in sorted(rules):
            bucket, _ = AttemptBucket.objects.select_for_update().get_or_create(
                key=key, defaults={"expires_at": end},
            )
            buckets.append(bucket)
            if bucket.count >= maximum:
                wait = max(wait, max(1, int(end.timestamp() - now) + 1))
        if not wait:
            for bucket in buckets:
                bucket.count += 1
                bucket.save(update_fields=["count"])
    if wait:
        raise Throttled(wait=wait)


def request_ip(request):
    # Configure a trusted reverse proxy before replacing REMOTE_ADDR.
    return request.META.get("REMOTE_ADDR", "unknown")
