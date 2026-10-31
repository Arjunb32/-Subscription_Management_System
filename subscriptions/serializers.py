from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from accounts.models import User
from products.models import Product, ProductVariant
from .api_common import StrictModelSerializer, domain_error
from .models import Plan, TaxRule, QuotationTemplate, QuotationTemplateLine, Subscription, SubscriptionLine, money
from .services import save_subscription, snapshot_line, permitted_actions


class PlanSerializer(StrictModelSerializer):
    class Meta:
        model = Plan
        exclude = ["fee_product"]

    def validate(self, attrs):
        start = attrs.get("available_from", getattr(self.instance, "available_from", None))
        end = attrs.get("available_until", getattr(self.instance, "available_until", None))
        if start and end and end < start:
            raise serializers.ValidationError({"available_until": "Must be on or after available_from."})
        return attrs


class TaxSerializer(StrictModelSerializer):
    class Meta:
        model = TaxRule
        fields = ["id", "name", "rate", "is_active"]


class LineInput(StrictModelSerializer):
    base_unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False, write_only=True)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    tax_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = QuotationTemplateLine
        fields = ["id", "product", "product_variant", "quantity", "base_unit_price", "unit_price", "tax_rule", "tax_rate", "description", "amount", "tax_amount"]
        read_only_fields = ["id", "tax_rate", "description"]

    def validate(self, attrs):
        try:
            snapshot_line(attrs)
        except Exception as exc:
            domain_error(exc)
        return attrs


class TemplateSerializer(StrictModelSerializer):
    lines = LineInput(many=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True)

    class Meta:
        model = QuotationTemplate
        fields = ["id", "name", "plan", "plan_name", "validity_days", "is_active", "lines"]

    def validate(self, attrs):
        plan = attrs.get("plan", getattr(self.instance, "plan", None))
        lines = attrs.get("lines")
        if plan and not plan.is_active:
            raise serializers.ValidationError({"plan": "Plan is archived."})
        quantities = [line["quantity"] for line in lines] if lines is not None else list(self.instance.lines.values_list("quantity", flat=True))
        if not quantities or sum(quantities, Decimal(0)) < plan.min_quantity:
            raise serializers.ValidationError({"lines": "Template must meet the plan minimum quantity."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines")
        template = QuotationTemplate.objects.create(**validated_data)
        self.save_lines(template, lines)
        return template

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = QuotationTemplate.objects.select_for_update().get(pk=instance.pk)
        lines = validated_data.pop("lines", None)
        instance = super().update(instance, validated_data)
        if lines is not None:
            instance.lines.all().delete()
            self.save_lines(instance, lines)
        return instance

    def save_lines(self, template, lines):
        for data in lines:
            QuotationTemplateLine.objects.create(template=template, **snapshot_line(data))


class SubscriptionWriteSerializer(StrictModelSerializer):
    lines = LineInput(many=True, required=False, max_length=100)
    customer = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(role="customer", is_active=True))
    plan = serializers.PrimaryKeyRelatedField(queryset=Plan.objects.all(), required=False)

    class Meta:
        model = Subscription
        fields = ["customer", "plan", "template", "start_date", "expiry_date", "payment_terms_days", "validity_days", "lines"]

    def create(self, validated_data):
        try:
            return save_subscription(validated_data)
        except Exception as exc:
            domain_error(exc)

    def update(self, instance, validated_data):
        try:
            return save_subscription(validated_data, instance=instance)
        except Exception as exc:
            domain_error(exc)


class SubscriptionLineSerializer(LineInput):
    class Meta(LineInput.Meta):
        model = SubscriptionLine
        fields = LineInput.Meta.fields + ["is_plan_fee"]
        read_only_fields = fields


class SubscriptionSerializer(serializers.ModelSerializer):
    customer_email = serializers.EmailField(source="customer.email", read_only=True)
    customer_display = serializers.SerializerMethodField()
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    currency = serializers.SerializerMethodField()
    renewal_date = serializers.DateField(source="current_period_end", read_only=True)
    price = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()
    permitted_actions = serializers.SerializerMethodField()
    lines = SubscriptionLineSerializer(many=True, read_only=True)

    class Meta:
        model = Subscription
        fields = ["id", "subscription_number", "customer", "customer_email", "customer_display", "plan", "plan_name", "status", "start_date", "expiry_date", "current_period_start", "current_period_end", "renewal_date", "payment_terms_days", "quotation_valid_until", "plan_price", "billing_interval", "currency", "subtotal", "price", "permitted_actions", "lines"]

    def get_customer_display(self, obj):
        return obj.customer.get_full_name() or obj.customer.email

    def get_currency(self, obj):
        return "INR"

    def get_subtotal(self, obj):
        return str(money(sum((line.amount for line in obj.lines.all()), Decimal(0))))

    def get_price(self, obj):
        return str(money(sum((line.amount + line.tax_amount for line in obj.lines.all()), Decimal(0))))

    def get_permitted_actions(self, obj):
        return permitted_actions(obj, self.context["request"].user)
