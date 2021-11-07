import random
from decimal import Decimal
from django.test import TestCase

from django_scopes import scopes_disabled
from shared_models.models import Profile, Product, Cart, Coupon

from campuslibs.cart.common import coupon_apply, create_cart, get_discounts, get_store_from_product, tax_apply

class CreateCartTestCase(TestCase):

    def test_non_persistent_cart(self):
        profile = Profile.objects.first()
        products = Product.objects.all()[:1]
        store = get_store_from_product(products)
        self.assertIsNone(create_cart(store, products, Decimal('0.0'), profile, False))

    def test_persistent_cart(self):
        profile = Profile.objects.first()
        products = Product.objects.all()[:1]
        store = get_store_from_product(products)
        self.assertIsInstance(create_cart(store, products, Decimal('0.0'), profile, True), Cart)


class DiscountTestCase(TestCase):

    def test_percentage_coupon(self):
        with scopes_disabled():
            coupon = Coupon.objects.filter(coupon_type='percentage').first()
        price, discount = get_discounts(coupon, Decimal('100.00'))
        self.assertLess(discount, Decimal('100.00'))

    def test_fixed_coupon(self):
        with scopes_disabled():
            coupon = Coupon.objects.filter(coupon_type='fixed').first()
        price, discount = get_discounts(coupon, Decimal('100.00'))
        self.assertLess(discount, Decimal('100.00'))


class CouponTestCase(TestCase):

    def test_coupon_on_persistent_cart(self):
        with scopes_disabled():
            coupon = Coupon.objects.filter(coupon_type='percentage').first()
        profile = Profile.objects.first()
        with scopes_disabled():
            cart = Cart.objects.first()
        coupon, discount, msg = coupon_apply(coupon.code, Decimal('100.00'), profile, cart)

        self.assertLess(discount, Decimal('100.00'))

    def test_coupon_on_non_persistent_cart(self):
        with scopes_disabled():
            coupon = Coupon.objects.filter(coupon_type='percentage').first()
        profile = Profile.objects.first()
        cart = None
        coupon, discount, msg = coupon_apply(coupon.code, Decimal('100.00'), profile, cart)

        self.assertLess(discount, Decimal('100.00'))


class TaxTestCase(TestCase):

    def test_empty_zip_code(self):
        with scopes_disabled():
            cart = Cart.objects.first()

        products = Product.objects.filter(id__in=cart.cart_items.all().values_list('product'))
        zip_code = None
        sales_tax, msg = tax_apply(zip_code, products, cart)

        self.assertLess(sales_tax, Decimal('100.00'))

    def test_real_zip_code(self):
        with scopes_disabled():
            cart = Cart.objects.first()
        products = Product.objects.filter(id__in=cart.cart_items.all().values_list('product'))
        zip_codes = [
            '35816', '99524', '85055', '72217', '90213', '80239',
            '06112', '19905', '20020', '32837', '30381', '96830',
            '83254', '62709', '46209', '50323', '67221', '41702',
            '70119', '04034', '21237', '02137', '49735', '55808',
            '39535', '63141', '59044', '68902', '89513', '03217',
            '07039', '87506', '10048', '27565', '58282', '44179',
            '74110', '97225', '15244', '02841', '29020', '57402',
            '37222', '78705', '84323', '05751', '24517', '98009',
            '25813', '53228', '82941'
        ]
        zip_code = random.choice(zip_codes)
        sales_tax, msg = tax_apply(zip_code, products, cart)

        self.assertEqual(sales_tax, cart.sales_tax)
