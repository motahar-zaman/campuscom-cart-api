from django.test import TestCase
from cart.views.add import coupon_apply

class CouponTestCase(TestCase):

    def test_empty_coupon(self):
        self.assertEqual(coupon_apply('coupon_code', 'total_amount', 'profile', 'cart'), 5)

    # def test_none_coupon(self):
    #     self.assertEqual(coupon_apply(), ())

    # def test_wrong_coupon(self):
    #     self.assertEqual(coupon_apply(), ())
