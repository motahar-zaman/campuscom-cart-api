from decimal import Decimal
from django.test import TestCase

from django_scopes import scopes_disabled
from shared_models.models import Profile, Product, Cart, Coupon

from cart.views.add import create_cart, get_discounts, coupon_apply

class CreateCartTestCase(TestCase):

    def test_non_persistent_cart(self):
        profile = Profile.objects.first()
        products = Product.objects.all()[:10]
        self.assertIsNone(create_cart(products, Decimal('0.0'), profile, False))

    def test_persistent_cart(self):
        profile = Profile.objects.first()
        products = Product.objects.all()[:10]
        self.assertIsInstance(create_cart(products, Decimal('0.0'), profile, True), Cart)


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
