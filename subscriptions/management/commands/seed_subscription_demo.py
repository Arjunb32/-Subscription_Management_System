"""Repeatable two-customer demo in a named disposable test database."""
import json
import secrets
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from billing.models import Invoice
from billing.services import generate_invoice_for_subscription, confirm_invoice, record_payment, cancel_invoice
from products.models import Product, ProductVariant
from subscriptions.calendar import add_interval
from subscriptions.models import Plan, TaxRule, QuotationTemplate, QuotationTemplateLine, Subscription
from subscriptions.services import save_subscription, transition


class Command(BaseCommand):
    help = "Create reproducible +560 variant demo. Refuses the working database."

    def add_arguments(self, parser):
        parser.add_argument('--complete-workflow', action='store_true')
        parser.add_argument('--browser-credentials', action='store_true', help='Generate disposable passwords in ignored .local/demo-browser.json (never prints them).')

    @transaction.atomic
    def handle(self, *args, **options):
        if settings.DATABASES['default']['NAME'] != 'test_subscription_demo':
            raise CommandError('Use config.demo_settings and the isolated PostgreSQL cluster. Working database refused.')
        local_file = Path(settings.BASE_DIR) / '.local' / 'demo-browser.json'
        credentials = json.loads(local_file.read_text()) if local_file.exists() else {}
        users = {}
        for label, role in (('admin','admin'),('staff','staff'),('customer-a','customer'),('customer-b','customer')):
            email=f'demo-{label}@example.test'
            user, created=User.objects.get_or_create(email=email, defaults={'role':role})
            if user.role != role:
                raise CommandError('Existing demo account has a different role; refusing to modify it.')
            if created:
                user.set_unusable_password();user.save(update_fields=['password'])
            if options['browser_credentials']:
                credentials.setdefault(label, {'email':email,'password':f'Demo!Aa9{secrets.token_urlsafe(24)}'})
                user.set_password(credentials[label]['password']);user.save(update_fields=['password'])
            users[label]=user
        today=timezone.localdate()
        year,month=today.year,today.month-2
        while month<1:year,month=year-1,month+12
        start=date(year,month,1)
        product,_=Product.objects.get_or_create(name='Demo Odoo license',defaults={'sales_price':1000,'cost_price':400,'notes':'Demo internal catalog note'})
        variant,_=ProductVariant.objects.get_or_create(product=product,name='Enterprise +560',defaults={'price_extra':560,'values':{'edition':'Enterprise'}})
        tax,_=TaxRule.objects.get_or_create(name='Demo GST 18%',defaults={'rate':18})
        plan,_=Plan.objects.get_or_create(name='Demo monthly',defaults={'price':100,'allow_customer_accept':True,'allow_pause':True,'allow_renewal':True,'allow_early_close':True})
        template,created=QuotationTemplate.objects.get_or_create(name='Demo enterprise quotation',defaults={'plan':plan,'validity_days':14})
        if created:
            QuotationTemplateLine.objects.create(template=template,product=product,product_variant=variant,quantity=1,unit_price=Decimal('1560'),tax_rule=tax,tax_rate=18,description=str(variant))
        expiry=start
        for _ in range(6):expiry=add_interval(expiry,'monthly')
        for label in ('customer-a','customer-b'):
            sub=Subscription.objects.filter(customer=users[label],template=template).first()
            if not sub:
                sub=save_subscription({'customer':users[label],'template':template,'start_date':start,'expiry_date':expiry,'payment_terms_days':0})
            if options['complete_workflow'] and sub.status=='draft':
                transition(sub.pk,'quote',users['staff'])
                transition(sub.pk,'confirm',users[label])
                transition(sub.pk,'activate',users['staff'])
                for index in range(2):
                    sub.refresh_from_db()
                    invoice=generate_invoice_for_subscription(sub.pk,sub.current_period_end)
                    if label=='customer-b' and index==0:
                        cancel_invoice(invoice.pk)
                    else:
                        confirm_invoice(invoice.pk)
                        if label=='customer-a':
                            amount=invoice.total if index==0 else Decimal('500.00')
                            record_payment(invoice.pk,amount=amount,method='bank_transfer',date=invoice.issue_date,recorded_by=users['staff'])
        if options['browser_credentials']:
            local_file.parent.mkdir(exist_ok=True)
            local_file.write_text(json.dumps(credentials),encoding='utf-8')
            self.stdout.write('Disposable browser credentials saved locally in ignored .local/demo-browser.json; no passwords printed.')
        self.stdout.write('Demo ready: 2 customers, +560 variant, INR 100 plan fee, 18% product tax. Workflow reruns preserve existing records.')
        self.stdout.write(f'Demo subscriptions: {Subscription.objects.filter(template=template).count()}; invoices: {Invoice.objects.filter(subscription__template=template).count()}.')
