"""Bounded, repeatable performance fixtures in an explicitly disposable DB."""
import json
import platform
import statistics
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.test import Client
from rest_framework.test import APIClient

from accounts.models import User
from billing.models import Invoice, InvoiceLine, Payment
from products.models import Product, ProductVariant
from subscriptions.models import Plan, TaxRule, Subscription, SubscriptionLine


class Command(BaseCommand):
    help = "Benchmark real production app responses with 5,000 subscriptions in test_subscription_perf."

    def handle(self, *args, **options):
        if settings.DATABASES['default']['NAME'] != 'test_subscription_perf':
            raise CommandError('Use config.performance_settings; all other databases are refused.')
        staff,_=User.objects.get_or_create(email='perf-staff@example.test',defaults={'role':'staff','password':'!'})
        a,_=User.objects.get_or_create(email='perf-a@example.test',defaults={'password':'!'})
        b,_=User.objects.get_or_create(email='perf-b@example.test',defaults={'password':'!'})
        with transaction.atomic():
            if not Subscription.objects.filter(subscription_number='PERF-000000').exists():
                product=Product.objects.create(name='Performance license',sales_price=1000)
                variant=ProductVariant.objects.create(product=product,name='Enterprise',price_extra=560)
                tax=TaxRule.objects.create(name='Performance GST',rate=18)
                plan=Plan.objects.create(name='Performance monthly',price=100)
                subs=Subscription.objects.bulk_create([Subscription(subscription_number=f'PERF-{index:06}',customer=a if index%2 else b,plan=plan,status='active',start_date=date(2026,1,1),current_period_start=date(2026,3,1),current_period_end=date(2026,4,1),plan_price=100) for index in range(5000)],batch_size=500)
                sub_lines=[]
                for sub in subs:
                    sub_lines += [SubscriptionLine(subscription=sub,product=product,product_variant=variant,quantity=1,unit_price=1560,tax_rule=tax,tax_rate=18,description='Performance enterprise'),SubscriptionLine(subscription=sub,product=plan.fee_product,quantity=1,unit_price=100,is_plan_fee=True,description='Plan fee')]
                SubscriptionLine.objects.bulk_create(sub_lines,batch_size=500)
                invoices=[]
                for index,sub in enumerate(subs):
                    for period in (1,2):
                        paid=Decimal('1940.80') if period==1 else Decimal('500')
                        invoices.append(Invoice(invoice_number=f'PERF-INV-{index:06}-{period}',subscription=sub,customer_id=sub.customer_id,issue_date=date(2026,period+1,1),due_date=date(2026,period+1,15),period_start=date(2026,period,1),period_end=date(2026,period+1,1),subtotal=1660,tax_amount=Decimal('280.80'),total=Decimal('1940.80'),amount_paid=paid,status='paid' if period==1 else 'confirmed'))
                Invoice.objects.bulk_create(invoices,batch_size=500)
                payments=[];invoice_lines=[]
                for invoice in invoices:
                    payments.append(Payment(invoice=invoice,amount=invoice.amount_paid,payment_method='bank_transfer',payment_date=invoice.issue_date,recorded_by=staff))
                    invoice_lines += [InvoiceLine(invoice=invoice,product=product,product_variant=variant,description='Performance enterprise',quantity=1,unit_price=1560,tax_rule=tax,tax_rate=18,tax_amount=Decimal('280.80'),line_total=Decimal('1840.80')),InvoiceLine(invoice=invoice,product=plan.fee_product,description='Plan fee',quantity=1,unit_price=100,line_total=100)]
                Payment.objects.bulk_create(payments,batch_size=500)
                InvoiceLine.objects.bulk_create(invoice_lines,batch_size=500)
        api=APIClient();api.force_authenticate(staff)
        pages=Client();pages.force_login(staff)
        samples=[]
        targets=[(api,'/api/subscriptions/'),(api,'/api/subscriptions/?page=200'),(api,'/api/subscriptions/?customer='+str(a.pk)),(api,'/api/billing/invoices/'),(api,'/api/billing/payments/'),(api,'/api/billing/dashboard/summary/'),(pages,'/dashboard/'),(pages,'/manage/subscriptions/')]
        customer_api=APIClient();customer_api.force_authenticate(a)
        customer_pages=Client();customer_pages.force_login(a)
        targets += [(customer_api,'/api/my/subscriptions/'),(customer_api,'/api/billing/my/invoices/'),(customer_api,'/api/billing/my/payments/'),(customer_pages,'/portal/')]
        for client,url in targets:
            durations=[]
            for _ in range(6):
                started=time.perf_counter();response=client.get(url);durations.append((time.perf_counter()-started)*1000)
                if response.status_code!=200:raise CommandError(f'Unexpected {response.status_code} at {url}')
            samples.append({'url':url,'cold_ms':round(durations[0],2),'median_ms':round(statistics.median(durations[1:]),2),'max_warm_ms':round(max(durations[1:]),2)})
        with connection.cursor() as cursor:
            cursor.execute('SHOW server_version');pg=cursor.fetchone()[0]
        result={'environment':{'os':platform.platform(),'python':platform.python_version(),'postgresql':pg,'database':'test_subscription_perf','method':'Django request/response client, local PostgreSQL; 1 cold + 5 warm requests each. No browser rendering or network latency.'},'dataset':{'subscriptions':Subscription.objects.count(),'subscription_lines':SubscriptionLine.objects.count(),'invoices':Invoice.objects.count(),'invoice_lines':InvoiceLine.objects.count(),'payments':Payment.objects.count(),'customers':2},'measurements':samples,'under_2s_backend':all(max(row['cold_ms'],row['max_warm_ms'])<2000 for row in samples)}
        output=Path(settings.BASE_DIR)/'.local'/'subscription-performance.json'
        output.write_text(json.dumps(result,indent=2))
        self.stdout.write(json.dumps(result,indent=2))
