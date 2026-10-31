"""Transactional writes. Catalog and quotation snapshots are never repriced by billing."""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .calendar import add_interval
from .models import Plan, Subscription, SubscriptionLine, SubscriptionEvent, money

POLICIES = ("allow_pause", "allow_customer_accept", "allow_renewal", "allow_early_close", "auto_close")


def snapshot_line(data):
    data = dict(data)
    product = data["product"]
    variant = data.get("product_variant")
    tax = data.get("tax_rule")
    if product.is_system or not product.is_active:
        raise ValidationError({"product": "Choose an active catalog product."})
    if variant and (variant.product_id != product.pk or not variant.is_active):
        raise ValidationError({"product_variant": "Choose an active variant of the selected product."})
    if tax and not tax.is_active:
        raise ValidationError({"tax_rule": "Choose an active tax rule."})
    base = data.pop("base_unit_price", product.sales_price)
    data["unit_price"] = money(base + (variant.price_extra if variant else Decimal(0)))
    if data["unit_price"] > Decimal("99999999.99"):
        raise ValidationError({"base_unit_price": "Combined price is too large."})
    data["tax_rate"] = tax.rate if tax else Decimal(0)
    data["description"] = str(variant or product)
    return data


def validate_dates(sub):
    if sub.expiry_date:
        # Expiry is a service boundary, exclusive. No unagreed partial-period charge.
        boundary = sub.current_period_end
        for _ in range(36600):
            if boundary >= sub.expiry_date:
                break
            boundary = add_interval(boundary, sub.billing_interval)
        if boundary != sub.expiry_date:
            raise ValidationError({"expiry_date": "Expiry must be a complete billing-period boundary (within 100 years)."})


def validate_ready(sub, *, check_catalog=True):
    lines = list(sub.lines.all())
    real_lines = [line for line in lines if not line.is_plan_fee]
    if not real_lines or sum((line.quantity for line in real_lines), Decimal(0)) < sub.min_quantity:
        raise ValidationError({"lines": f"Add product lines totaling at least {sub.min_quantity} units."})
    if len([line for line in lines if line.is_plan_fee]) != 1:
        raise ValidationError({"lines": "Exactly one snapshotted plan fee is required."})
    for line in lines:
        line.full_clean()
    if sum((line.amount + line.tax_amount for line in lines), Decimal(0)) > Decimal("99999999.99"):
        raise ValidationError({"lines": "Per-period total exceeds the supported INR 99,999,999.99 limit."})
    if check_catalog:
        plan = sub.plan
        if not plan.is_active or (plan.available_from and sub.start_date < plan.available_from) or (plan.available_until and sub.start_date > plan.available_until):
            raise ValidationError({"plan": "Plan is unavailable for this start date."})
    if sub.current_period_end <= sub.current_period_start or sub.start_date != sub.current_period_start:
        raise ValidationError({"start_date": "Invalid initial service dates."})
    validate_dates(sub)


def refresh_plan_snapshot(sub):
    plan = sub.plan
    sub.plan_price = plan.price
    sub.billing_interval = plan.billing_interval
    sub.min_quantity = plan.min_quantity
    for key in POLICIES:
        setattr(sub, key, getattr(plan, key))
    sub.current_period_start = sub.start_date
    sub.current_period_end = add_interval(sub.start_date, sub.billing_interval)


@transaction.atomic
def save_subscription(data, *, instance=None):
    data = dict(data)
    lines = data.pop("lines", None)
    template = data.pop("template", None)
    if instance:
        sub = Subscription.objects.select_for_update().get(pk=instance.pk)
        if sub.status != "draft":
            raise ValidationError({"detail": "Only drafts can be edited. Create a new quotation for changed terms."})
        if template:
            raise ValidationError({"template": "Apply templates only when creating a draft."})
    else:
        sub = Subscription()
    if template:
        if not template.is_active:
            raise ValidationError({"template": "Template is archived."})
        if data.get("plan") and data["plan"] != template.plan:
            raise ValidationError({"plan": "Plan must match the template."})
        if lines is not None:
            raise ValidationError({"lines": "Choose template lines or custom lines."})
        data["plan"] = template.plan
        data["validity_days"] = template.validity_days
        sub.template = template
    for key, value in data.items():
        setattr(sub, key, value)
    if not sub.plan_id:
        raise ValidationError({"plan": "A plan or template is required."})
    if not sub.customer_id or sub.customer.role != "customer" or not sub.customer.is_active:
        raise ValidationError({"customer": "Choose an active customer account."})
    refresh_plan_snapshot(sub)
    if not sub.plan.is_active:
        raise ValidationError({"plan": "Plan is archived."})
    sub.full_clean()
    validate_dates(sub)
    sub.save()
    if lines is not None or template:
        sub.lines.filter(is_plan_fee=False).delete()
        if template:
            for line in template.lines.all():
                values = {key: getattr(line, key) for key in ("product", "product_variant", "quantity", "unit_price", "tax_rule", "tax_rate", "description")}
                SubscriptionLine.objects.create(subscription=sub, **values)
        else:
            for values in lines:
                line = SubscriptionLine(subscription=sub, **snapshot_line(values))
                line.full_clean()
                line.save()
    sub.lines.filter(is_plan_fee=True).delete()
    SubscriptionLine.objects.create(subscription=sub, product=sub.plan.fee_product, quantity=1, unit_price=sub.plan_price, is_plan_fee=True, description=f"Plan fee: {sub.plan.name}")
    return sub


def permitted_actions(sub, user):
    if not user.is_authenticated or not user.is_active:
        return []
    staff = user.role in ("admin", "staff")
    if not staff and (user.role != "customer" or sub.customer_id != user.pk):
        return []
    actions = []
    if staff and sub.status == "draft":
        actions += ["quote"]
    if sub.status == "quotation" and (staff or sub.allow_customer_accept):
        if sub.quotation_valid_until and sub.quotation_valid_until >= timezone.localdate():
            actions += ["confirm"]
    if staff and sub.status == "confirmed":
        actions += ["activate"]
    if sub.status == "active" and sub.allow_pause:
        actions += ["pause"]
    if sub.status == "paused" and sub.pause_reason == "manual" and sub.allow_pause:
        actions += ["resume"]
    if sub.status in ("active", "paused") and sub.expiry_date and sub.allow_renewal and sub.pause_reason != "manual":
        actions += ["renew"]
    if sub.status in ("active", "paused") and sub.allow_early_close:
        actions += ["close"]
    return actions


def settle_due_periods(sub, today):
    from billing.services import generate_invoice_for_subscription
    for _ in range(36):
        sub.refresh_from_db()
        if sub.status != "active" or sub.current_period_end > today:
            return
        if generate_invoice_for_subscription(sub.pk, today) is None:
            break
    sub.refresh_from_db()
    if sub.status == "active" and sub.current_period_end <= today:
        raise ValidationError({"detail": "More due periods remain. Run billing catch-up before this action."})


@transaction.atomic
def transition(subscription_id, action, user, *, today=None):
    today = today or timezone.localdate()
    sub = Subscription.objects.select_for_update().select_related("plan", "customer").get(pk=subscription_id)
    if action not in permitted_actions(sub, user):
        raise ValidationError({"action": "Transition is unavailable for this status, owner or snapshotted plan policy."})
    if action == "quote":
        validate_ready(sub)
        sub.status = "quotation"
        sub.quotation_valid_until = today + timedelta(days=sub.validity_days)
    elif action == "confirm":
        if not sub.quotation_valid_until or today > sub.quotation_valid_until:
            raise ValidationError({"detail": "Quotation has expired."})
        validate_ready(sub, check_catalog=False)
        sub.status = "confirmed"
    elif action == "activate":
        validate_ready(sub, check_catalog=False)
        if sub.start_date > today or (sub.expiry_date and sub.expiry_date <= today):
            raise ValidationError({"start_date": "Activation requires a started, unexpired service period."})
        sub.status = "active"
    elif action in ("pause", "close"):
        if sub.status == "active":
            settle_due_periods(sub, today)
            if sub.status != "active":
                return sub
        if today < sub.current_period_start:
            raise ValidationError({"detail": "Cannot change an invoiced future period."})
        if action == "pause":
            sub.status, sub.paused_on, sub.pause_reason = "paused", today, "manual"
        else:
            # Completed periods settled above. Unfinished period is waived, no proration.
            sub.status = "closed"
    elif action == "resume":
        duration = today - sub.paused_on
        if duration.days < 0:
            raise ValidationError({"detail": "Resume cannot precede pause."})
        future_periods = 0
        boundary = sub.current_period_end
        while sub.expiry_date and boundary < sub.expiry_date:
            boundary = add_interval(boundary, sub.billing_interval)
            future_periods += 1
        sub.current_period_end += duration
        if sub.expiry_date:
            sub.expiry_date = sub.current_period_end
            for _ in range(future_periods):
                sub.expiry_date = add_interval(sub.expiry_date, sub.billing_interval)
        sub.status, sub.paused_on, sub.pause_reason = "active", None, ""
    elif action == "renew":
        if sub.status == "active":
            settle_due_periods(sub, today)
        if sub.status == "closed":
            raise ValidationError({"detail": "Closed subscriptions are terminal. Renew before automatic closure."})
        if sub.pause_reason == "expiry" and today > sub.expiry_date:
            raise ValidationError({"detail": "Expired service cannot be renewed retroactively. Create a new quotation."})
        sub.expiry_date = add_interval(sub.expiry_date, sub.billing_interval)
        if sub.pause_reason == "expiry":
            sub.status, sub.pause_reason = "active", ""
    sub.full_clean()
    sub.save()
    SubscriptionEvent.objects.create(subscription=sub, action=action, actor=user, effective_date=today)
    return sub
