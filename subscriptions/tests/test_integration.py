from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from accounts.models import User
from billing.models import Discount, Invoice, Payment
from billing.services import bulk_generate_invoices, generate_invoice_for_subscription, record_payment, cancel_invoice
from products.models import Product, ProductVariant
from subscriptions.calendar import add_interval
from subscriptions.models import Plan, TaxRule, Subscription, SubscriptionLine
from subscriptions.serializers import TemplateSerializer
from subscriptions.services import save_subscription, transition


class SubscriptionIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user('integration-admin@example.test', 'TestPassword!9', role='admin')
        cls.staff = User.objects.create_user('integration-staff@example.test', 'TestPassword!9', role='staff')
        cls.a = User.objects.create_user('integration-a@example.test', 'TestPassword!9')
        cls.b = User.objects.create_user('integration-b@example.test', 'TestPassword!9')
        cls.product = Product.objects.create(name='Odoo', sales_price=Decimal('1000'), cost_price=Decimal('100'), notes='Private margin')
        cls.other_product = Product.objects.create(name='Other', sales_price=1)
        cls.variant = ProductVariant.objects.create(product=cls.product, name='Enterprise', price_extra=560, values={'edition':'Enterprise'})
        cls.tax = TaxRule.objects.create(name='GST', rate=18)
        cls.plan = Plan.objects.create(name='Monthly', price=100, allow_pause=True, allow_customer_accept=True, allow_renewal=True, allow_early_close=True)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        self.clock = patch('subscriptions.services.timezone.localdate', return_value=date(2026,1,1))
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def draft(self, **extra):
        data = dict(customer=self.a, plan=self.plan, start_date=date(2026,1,1), payment_terms_days=0, lines=[dict(product=self.product,product_variant=self.variant,quantity=Decimal(1),tax_rule=self.tax)])
        data.update(extra)
        return save_subscription(data)

    def active(self, **extra):
        sub = self.draft(**extra)
        for action in ('quote','confirm','activate'):
            sub = transition(sub.pk, action, self.staff)
        return sub

    def action(self, sub, operation, data=None):
        return self.client.post(f'/api/subscriptions/{sub.pk}/actions/{operation}/', data or {}, format='json')

    def test_real_model_workflow_variant_plan_fee_taxes_partial_full_payment_and_summary(self):
        sub = self.active()
        self.assertEqual(sub.lines.get(is_plan_fee=False).unit_price, Decimal('1560'))
        self.assertEqual(sub.lines.get(is_plan_fee=True).unit_price, Decimal('100'))
        invoice = generate_invoice_for_subscription(sub.pk, date(2026,2,1))
        self.assertEqual(invoice.customer, self.a)
        self.assertEqual(invoice.due_date, date(2026,2,1))
        self.assertEqual(invoice.subtotal, Decimal('1660'))
        self.assertEqual(invoice.tax_amount, Decimal('280.80'))
        self.assertEqual(invoice.total, Decimal('1940.80'))
        line = invoice.lines.get(product_variant=self.variant)
        self.assertEqual((line.quantity,line.unit_price,line.tax_rate), (Decimal(1), Decimal('1560'),Decimal(18)))
        self.assertIsNone(generate_invoice_for_subscription(sub.pk,date(2026,2,1)))
        self.assertEqual(self.client.post(f'/api/billing/invoices/{invoice.pk}/confirm/',{},format='json').status_code,200)
        record_payment(invoice.pk, amount=Decimal(500), method='cash',date=date(2026,2,1))
        summary=self.client.get('/api/billing/dashboard/summary/').json()
        self.assertEqual(summary['payments_collected'],'500.00')
        self.assertEqual(summary['total_outstanding'],'1440.80')
        with self.assertRaises(ValidationError):
            record_payment(invoice.pk,amount=Decimal(1500),method='cash',date=date(2026,2,1))
        with self.assertRaises(ValidationError):
            cancel_invoice(invoice.pk)
        record_payment(invoice.pk,amount=Decimal('1440.80'),method='cash',date=date(2026,2,1))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status,'paid')
        self.assertEqual(self.client.get('/api/billing/dashboard/summary/').json()['total_outstanding'],'0.00')

    def test_template_and_quotation_preserve_catalog_tax_and_plan_snapshots(self):
        serializer = TemplateSerializer(data={'name':'Reusable','plan':self.plan.pk,'validity_days':5,'lines':[{'product':self.product.pk,'product_variant':self.variant.pk,'quantity':'1.00','tax_rule':self.tax.pk}]})
        self.assertTrue(serializer.is_valid(),serializer.errors)
        template=serializer.save()
        Product.objects.filter(pk=self.product.pk).update(sales_price=9000)
        ProductVariant.objects.filter(pk=self.variant.pk).update(price_extra=999)
        TaxRule.objects.filter(pk=self.tax.pk).update(rate=40)
        sub=self.draft(template=template,plan=self.plan,lines=None)
        transition(sub.pk,'quote',self.staff)
        Plan.objects.filter(pk=self.plan.pk).update(price=888,billing_interval='daily',allow_pause=False)
        transition(sub.pk,'confirm',self.a)
        transition(sub.pk,'activate',self.staff)
        invoice=generate_invoice_for_subscription(sub.pk,date(2026,2,1))
        self.assertEqual(invoice.total,Decimal('1940.80'))
        self.assertEqual(invoice.lines.get(product_variant=self.variant).tax_rate,Decimal(18))
        sub.refresh_from_db()
        self.assertTrue(sub.allow_pause)
        self.assertEqual(sub.current_period_end,date(2026,3,1))
        line=invoice.lines.get(product_variant=self.variant)
        line.calculate();line.save()
        self.assertEqual(line.tax_rate,Decimal(18))

    def test_mismatched_variant_and_nonpositive_quantities_rejected(self):
        for values in ({'product':self.other_product.pk,'product_variant':self.variant.pk,'quantity':'1'}, {'product':self.product.pk,'quantity':'0'}, {'product':self.product.pk,'quantity':'-1'}):
            response=self.client.post('/api/subscriptions/',{'customer':self.a.pk,'plan':self.plan.pk,'start_date':'2026-01-01','lines':[values]},format='json')
            self.assertEqual(response.status_code,400,response.content)
        self.assertEqual(Subscription.objects.count(),0)

    def test_expired_quotation_cannot_be_accepted(self):
        sub=self.draft(validity_days=1)
        transition(sub.pk,'quote',self.staff)
        with self.assertRaises(ValidationError):
            transition(sub.pk,'confirm',self.a,today=date(2026,1,3))
        sub.refresh_from_db();self.assertEqual(sub.status,'quotation')

    def test_required_transitions_and_arbitrary_status_update_rejected(self):
        sub=self.draft()
        self.assertEqual(self.action(sub,'activate').status_code,400)
        response=self.client.patch(f'/api/subscriptions/{sub.pk}/',{'status':'active'},format='json')
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.action(sub,'quote').status_code,200)
        self.assertEqual(self.action(sub,'quote').status_code,400)
        self.assertEqual(self.action(sub,'confirm').status_code,200)
        self.assertEqual(self.action(sub,'activate').status_code,200)
        self.assertEqual(self.action(sub,'close').status_code,200)
        self.assertEqual(self.action(sub,'renew').status_code,400)

    def test_empty_lines_and_plan_minimum_prevent_quotation(self):
        sub=self.draft(lines=[])
        self.assertEqual(self.action(sub,'quote').status_code,400)
        Plan.objects.filter(pk=self.plan.pk).update(min_quantity=2)
        self.plan.refresh_from_db()
        sub=self.draft()
        self.assertEqual(self.action(sub,'quote').status_code,400)

    def test_plan_availability_and_archive_prevent_new_agreements(self):
        Plan.objects.filter(pk=self.plan.pk).update(available_from=date(2026,2,1))
        self.plan.refresh_from_db()
        sub=self.draft()
        self.assertEqual(self.action(sub,'quote').status_code,400)
        Plan.objects.filter(pk=self.plan.pk).update(is_active=False)
        self.plan.refresh_from_db()
        with self.assertRaises(ValidationError):self.draft()

    def test_expiry_requires_complete_cycle_and_future_start_cannot_activate(self):
        with self.assertRaises(ValidationError):self.draft(expiry_date=date(2026,1,20))
        sub=self.draft(start_date=date(2026,2,1))
        transition(sub.pk,'quote',self.staff)
        transition(sub.pk,'confirm',self.staff)
        self.assertEqual(self.action(sub,'activate').status_code,400)

    def test_pause_skips_billing_and_resume_preserves_service_duration(self):
        sub=self.active(expiry_date=date(2026,3,1))
        transition(sub.pk,'pause',self.a,today=date(2026,1,15))
        self.assertIsNone(generate_invoice_for_subscription(sub.pk,date(2026,2,10)))
        sub=transition(sub.pk,'resume',self.a,today=date(2026,1,25))
        self.assertEqual(sub.current_period_end,date(2026,2,11))
        self.assertEqual(sub.expiry_date,date(2026,3,11))
        self.assertIsNone(generate_invoice_for_subscription(sub.pk,date(2026,2,1)))
        self.assertIsNotNone(generate_invoice_for_subscription(sub.pk,date(2026,2,11)))

    def test_pause_settles_completed_arrears_and_never_rewrites_invoice(self):
        sub=self.active()
        transition(sub.pk,'pause',self.a,today=date(2026,3,10))
        self.assertEqual(sub.invoices.count(),2)
        dates=list(sub.invoices.values_list('period_start','period_end'))
        transition(sub.pk,'resume',self.a,today=date(2026,3,20))
        self.assertEqual(list(sub.invoices.values_list('period_start','period_end')),dates)

    def test_pause_month_end_expiry_stays_on_shifted_boundary(self):
        with patch('subscriptions.services.timezone.localdate',return_value=date(2025,1,31)):
            sub=self.active(start_date=date(2025,1,31),expiry_date=date(2025,3,28))
        transition(sub.pk,'pause',self.staff,today=date(2025,2,10))
        sub=transition(sub.pk,'resume',self.staff,today=date(2025,2,25))
        self.assertEqual(sub.current_period_end,date(2025,3,15))
        self.assertEqual(sub.expiry_date,date(2025,4,15))

    def test_renew_extends_expiry_without_advancing_billing_period(self):
        sub=self.active(expiry_date=date(2026,3,1))
        sub=transition(sub.pk,'renew',self.a)
        self.assertEqual(sub.expiry_date,date(2026,4,1))
        self.assertEqual(sub.current_period_end,date(2026,2,1))

    def test_auto_close_true_and_false_stop_billing_at_expiry(self):
        for auto in (True,False):
            self.plan.auto_close=auto;self.plan.save()
            sub=self.active(expiry_date=date(2026,2,1))
            invoice=generate_invoice_for_subscription(sub.pk,date(2026,4,1))
            self.assertIsNotNone(invoice)
            sub.refresh_from_db()
            self.assertEqual(sub.status,'closed' if auto else 'paused')
            self.assertIsNone(generate_invoice_for_subscription(sub.pk,date(2026,4,1)))
            if not auto:
                with self.assertRaises(ValidationError):transition(sub.pk,'renew',self.a,today=date(2026,2,2))
                renewed=transition(sub.pk,'renew',self.a,today=date(2026,2,1))
                self.assertEqual(renewed.status,'active')

    def test_catch_up_cap_is_reported_and_repeated_runs_complete(self):
        self.plan.billing_interval='daily';self.plan.save()
        sub=self.active()
        response=self.client.post('/api/billing/invoices/generate/',{'billing_date':'2026-02-15'},format='json')
        self.assertEqual(response.json()['invoices_created'],36)
        self.assertEqual(response.json()['remaining_due_subscriptions'],1)
        self.assertEqual(len(bulk_generate_invoices(date(2026,2,15))),9)
        self.assertEqual(sub.invoices.count(),45)

    def test_early_close_waives_incomplete_period_after_settlement(self):
        sub=self.active()
        sub=transition(sub.pk,'close',self.a,today=date(2026,2,15))
        self.assertEqual(sub.status,'closed')
        self.assertEqual(sub.invoices.count(),1)

    def test_customer_a_b_lists_details_actions_writes_and_invoice_isolation(self):
        a=self.active();b=self.active(customer=self.b)
        inv=generate_invoice_for_subscription(b.pk,date(2026,2,1))
        self.client.force_authenticate(self.a)
        response=self.client.get('/api/my/subscriptions/?page_size=1').json()
        self.assertEqual(response['count'],1)
        self.assertEqual(response['results'][0]['id'],a.pk)
        self.assertNotIn('cost_price',str(response))
        self.assertNotIn('Private margin',str(response))
        for base in ('/api/my/subscriptions/','/api/subscriptions/'):
            self.assertEqual(self.client.get(f'{base}{b.pk}/').status_code,404)
            self.assertEqual(self.client.post(f'{base}{b.pk}/actions/pause/',{},format='json').status_code,404)
        self.assertEqual(self.client.get('/api/subscriptions/').status_code,403)
        self.assertEqual(self.client.patch(f'/api/subscriptions/{a.pk}/',{'customer':self.b.pk},format='json').status_code,403)
        self.assertEqual(self.client.post('/api/subscriptions/',{'customer':self.b.pk,'template':999},format='json').status_code,403)
        self.assertEqual(self.client.get(f'/api/billing/invoices/{inv.pk}/').status_code,404)
        self.assertEqual(self.client.get('/api/billing/my/invoices/').json()['count'],0)

    def test_staff_can_reassign_only_draft_to_active_customer(self):
        sub=self.draft()
        url=f'/api/subscriptions/{sub.pk}/'
        self.assertEqual(self.client.patch(url,{'customer':self.staff.pk},format='json').status_code,400)
        self.assertEqual(self.client.patch(url,{'customer':self.b.pk},format='json').status_code,200)
        transition(sub.pk,'quote',self.staff)
        self.assertEqual(self.client.patch(url,{'customer':self.a.pk},format='json').status_code,400)

    def test_customer_actions_require_enabled_snapshotted_policy(self):
        self.plan.allow_pause=False;self.plan.allow_customer_accept=False;self.plan.save()
        sub=self.draft();transition(sub.pk,'quote',self.staff)
        self.client.force_authenticate(self.a)
        self.assertEqual(self.action(sub,'confirm').status_code,400)
        transition(sub.pk,'confirm',self.staff);transition(sub.pk,'activate',self.staff)
        self.assertEqual(self.action(sub,'pause').status_code,400)

    def test_tax_admin_permissions_percentage_and_reference_protection(self):
        data={'name':'New tax','rate':'18.00'}
        self.assertEqual(self.client.post('/api/tax-rules/',data,format='json').status_code,403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post('/api/tax-rules/',{**data,'rate':'101'},format='json').status_code,400)
        self.assertEqual(self.client.post('/api/tax-rules/',data,format='json').status_code,201)
        self.draft()
        self.assertEqual(self.client.delete(f'/api/tax-rules/{self.tax.pk}/').status_code,400)
        self.assertEqual(self.client.delete(f'/api/catalog/products/{self.product.pk}/').status_code,400)
        self.assertEqual(self.client.delete(f'/api/catalog/variants/{self.variant.pk}/').status_code,400)

    def test_variant_cannot_move_products_after_reference(self):
        self.draft()
        self.assertEqual(self.client.patch(f'/api/catalog/variants/{self.variant.pk}/',{'product':self.other_product.pk},format='json').status_code,400)

    def test_bounded_pagination_scoped_count_and_related_loading(self):
        for _ in range(4):self.draft()
        for _ in range(2):self.draft(customer=self.b)
        self.client.force_authenticate(self.a)
        with CaptureQueriesContext(connection) as queries:
            response=self.client.get('/api/my/subscriptions/?page_size=2')
        self.assertEqual(response.json()['count'],4)
        self.assertEqual(len(response.json()['results']),2)
        self.assertTrue(response.json()['next'])
        self.assertLessEqual(len(queries),5)
        Subscription.objects.bulk_create([Subscription(customer=self.a,plan=self.plan,start_date=date(2026,1,1),current_period_start=date(2026,1,1),current_period_end=date(2026,2,1)) for _ in range(120)])
        bounded=self.client.get('/api/my/subscriptions/?page_size=100000').json()
        self.assertEqual(len(bounded['results']),100)
        self.assertEqual(bounded['count'],124)
        self.assertEqual(self.client.get('/api/my/subscriptions/?customer=bad').status_code,400)

    def test_session_auth_csrf_and_management_page_role_checks(self):
        client=APIClient(enforce_csrf_checks=True)
        self.assertEqual(client.get('/api/subscriptions/').status_code,403)
        client.force_login(self.staff)
        self.assertEqual(client.post('/api/plans/',{'name':'CSRF'},format='json').status_code,403)
        for path in ('products','variants','plans','tax-rules','quotation-templates','subscriptions','invoices','payments','discounts'):
            self.assertEqual(client.get(f'/manage/{path}/').status_code,200)
        client.force_login(self.a)
        self.assertEqual(client.get('/manage/').status_code,403)

    def test_calendar_boundaries_and_explicit_half_up(self):
        self.assertEqual(add_interval(date(2028,1,31),'monthly'),date(2028,2,29))
        self.assertEqual(add_interval(date(2028,2,29),'yearly'),date(2029,2,28))
        self.plan.min_quantity=Decimal('.50');self.plan.save()
        sub=self.active(lines=[dict(product=self.product,quantity=Decimal('.50'),base_unit_price=Decimal('.01'),tax_rule=self.tax)])
        invoice=generate_invoice_for_subscription(sub.pk,date(2026,2,1))
        self.assertEqual(invoice.subtotal,Decimal('100.01'))

    def test_subscription_discount_allocated_before_tax(self):
        sub=self.active()
        Discount.objects.create(name='10%',discount_type='percentage',value=10,start_date=date(2026,1,1),applies_to='subscription')
        invoice=generate_invoice_for_subscription(sub.pk,date(2026,2,1))
        self.assertEqual(invoice.subtotal,Decimal('1660'))
        self.assertEqual(invoice.discount_amount,Decimal('166'))
        self.assertEqual(invoice.tax_amount,Decimal('252.72'))
        self.assertEqual(invoice.total,Decimal('1746.72'))

    def test_invoice_number_sequence_beyond_four_digits(self):
        sub=self.active()
        for index,number in enumerate(('9999','10000')):
            Invoice.objects.create(invoice_number=f'INV-202602-{number}',subscription=sub,customer=self.a,issue_date=date(2026,2,1),due_date=date(2026,2,1),period_start=date(2025,1+index,1),period_end=date(2025,2+index,1))
        invoice=generate_invoice_for_subscription(sub.pk,date(2026,2,1))
        self.assertEqual(invoice.invoice_number,'INV-202602-10001')

    def test_partial_nested_replacement_lines_require_product_and_default_quantity(self):
        sub=self.draft()
        url=f'/api/subscriptions/{sub.pk}/'
        bad=self.client.patch(url,{'lines':[{'quantity':'1.00'}]},format='json')
        self.assertEqual(bad.status_code,400)
        good=self.client.patch(url,{'lines':[{'product':self.product.pk}]},format='json')
        self.assertEqual(good.status_code,200,good.content)
        self.assertEqual(sub.lines.get(is_plan_fee=False).quantity,Decimal('1.00'))

    def test_malformed_billing_filters_are_validation_errors(self):
        for path in ('/api/billing/invoices/?customer=bad','/api/billing/invoices/?issue_date_from=not-a-date','/api/billing/payments/?invoice=bad','/api/billing/payments/?date_from=invalid'):
            self.assertEqual(self.client.get(path).status_code,400)

    def test_customer_invoice_and_payment_hide_internal_notes(self):
        sub=self.active()
        invoice=generate_invoice_for_subscription(sub.pk,date(2026,2,1))
        invoice.notes='Internal collection note';invoice.save(update_fields=['notes'])
        self.client.post(f'/api/billing/invoices/{invoice.pk}/confirm/',{},format='json')
        record_payment(invoice.pk,amount=Decimal(1),method='cash',date=date(2026,2,1),note='Internal payment note',recorded_by=self.staff)
        self.client.force_authenticate(self.a)
        self.assertNotIn('notes',self.client.get(f'/api/billing/invoices/{invoice.pk}/').json())
        payment=self.client.get('/api/billing/my/payments/').json()['results'][0]
        self.assertNotIn('note',payment)
        self.assertNotIn('recorded_by_email',payment)

    def test_actions_reject_browser_supplied_effective_dates(self):
        sub=self.active()
        self.assertEqual(self.action(sub,'pause',{'today':'2030-01-01'}).status_code,400)
        sub.refresh_from_db();self.assertEqual(sub.status,'active')

    def test_pause_catch_up_limit_rolls_back_instead_of_skipping_due_periods(self):
        self.plan.billing_interval='daily';self.plan.save()
        sub=self.active()
        with self.assertRaises(ValidationError):transition(sub.pk,'pause',self.a,today=date(2026,2,15))
        self.assertEqual(sub.invoices.count(),0)
        sub.refresh_from_db();self.assertEqual(sub.current_period_end,date(2026,1,2))

    def test_discount_thresholds_and_expiry_are_respected(self):
        sub=self.active()
        Discount.objects.create(name='Too much minimum',discount_type='fixed',value=500,min_purchase=2000,start_date=date(2026,1,1),applies_to='subscription')
        Discount.objects.create(name='Too many seats',discount_type='fixed',value=500,min_quantity=3,start_date=date(2026,1,1),applies_to='product')
        expired=Discount.objects.create(name='Expired',discount_type='fixed',value=500,start_date=date(2026,1,1),end_date=date(2026,1,31),applies_to='subscription')
        invoice=generate_invoice_for_subscription(sub.pk,date(2026,2,1))
        self.assertIsNone(invoice.discount)
        self.assertEqual(invoice.total,Decimal('1940.80'))

    def test_plan_fee_does_not_satisfy_product_quantity_discount_threshold(self):
        sub=self.active()
        Discount.objects.create(name='Two seats required',discount_type='fixed',value=500,min_quantity=2,start_date=date(2026,1,1),applies_to='subscription')
        invoice=generate_invoice_for_subscription(sub.pk,date(2026,2,1))
        self.assertIsNone(invoice.discount)
        self.assertEqual(invoice.total,Decimal('1940.80'))

    def test_per_period_overflow_is_rejected_before_activation(self):
        sub=self.draft(lines=[dict(product=self.product,quantity=Decimal(2),base_unit_price=Decimal('99999999.99'))])
        self.assertEqual(self.action(sub,'quote').status_code,400)

    def test_manual_invoice_endpoint_uses_engine_and_does_not_reserve_empty_period(self):
        sub=self.active()
        data={'subscription':sub.pk,'customer':self.a.pk,'issue_date':'2026-01-15','due_date':'2026-01-15','period_start':'2026-01-01','period_end':'2026-02-01'}
        self.assertEqual(self.client.post('/api/billing/invoices/',data,format='json').status_code,400)
        self.assertEqual(sub.invoices.count(),0)
        data.update(issue_date='2026-02-01',due_date='2026-02-01')
        result=self.client.post('/api/billing/invoices/',data,format='json')
        self.assertEqual(result.status_code,201,result.content)
        self.assertEqual(result.json()['total'],'1940.80')
        self.assertEqual(len(result.json()['lines']),2)

    def test_cancelled_invoice_has_no_collectible_balance(self):
        sub=self.active()
        invoice=generate_invoice_for_subscription(sub.pk,date(2026,2,1))
        invoice=cancel_invoice(invoice.pk)
        self.assertEqual(invoice.amount_due,Decimal('0.00'))
        self.assertEqual(invoice.total,Decimal('1940.80'))
        self.client.force_authenticate(self.a)
        result=self.client.get('/api/billing/my/invoices/').json()['results'][0]
        self.assertEqual(result['amount_due'],'0.00')
