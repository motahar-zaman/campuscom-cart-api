from decimal import Decimal
from django.test import TestCase
from cart.views.add import create_cart
from shared_models.models import Profile, Product

class CouponTestCase(TestCase):

    def test_non_persistent_cart(self):
        profile = Profile.objects.first()
        products = Product.objects.all()[:10]
        self.assertIsNone(create_cart(products, Decimal('0.0'), profile, False))

    def test_persistent_cart(self):
        profile = Profile.objects.first()
        products = Product.objects.all()[:10]
        self.assertEqual(create_cart(products, Decimal('0.0'), profile, True), None)
