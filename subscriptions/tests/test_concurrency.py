from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier

from django.db import close_old_connections
from django.test import TransactionTestCase

from accounts.models import User
from billing.models import Invoice
from billing.services import generate_invoice_for_subscription
from products.models import Product
from subscriptions.models import Plan, TaxRule
from subscriptions.services import save_subscription, transition


class IntegratedLifecycleConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.staff=User.objects.create_user('race-staff@example.test','TestPassword!9',role='staff')
        self.customer=User.objects.create_user('race-customer@example.test','TestPassword!9')
        product=Product.objects.create(name='Concurrent product',sales_price=1000)
        plan=Plan.objects.create(name='Concurrent plan',price=100,allow_pause=True)
        tax=TaxRule.objects.create(name='Concurrent tax',rate=18)
        self.sub=save_subscription({'customer':self.customer,'plan':plan,'start_date':date(2026,1,1),'lines':[{'product':product,'quantity':Decimal(1),'tax_rule':tax}]})
        for action in ('quote','confirm','activate'):
            self.sub=transition(self.sub.pk,action,self.staff)

    def run_pair(self, first, second):
        barrier=Barrier(2)
        def invoke(function):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return function()
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(invoke,function) for function in (first,second)]
            return [future.result(timeout=30) for future in futures]

    def test_concurrent_generation_from_real_accepted_quote_bills_fee_once(self):
        bill=lambda:generate_invoice_for_subscription(self.sub.pk,date(2026,2,1))
        results=self.run_pair(bill,bill)
        self.assertEqual(sum(result is not None for result in results),1)
        invoice=Invoice.objects.get(subscription=self.sub)
        self.assertEqual(invoice.total,Decimal('1280.00'))
        self.assertEqual(invoice.lines.filter(subscription_line__is_plan_fee=True).count(),1)

    def test_pause_racing_billing_settles_one_period_and_stays_paused(self):
        self.run_pair(lambda:generate_invoice_for_subscription(self.sub.pk,date(2026,2,1)),lambda:transition(self.sub.pk,'pause',self.customer,today=date(2026,2,1)))
        invoice=Invoice.objects.get(subscription=self.sub)
        self.assertEqual(invoice.total,Decimal('1280.00'))
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status,'paused')
        self.assertEqual(self.sub.current_period_start,date(2026,2,1))
        self.assertEqual(self.sub.current_period_end,date(2026,3,1))
