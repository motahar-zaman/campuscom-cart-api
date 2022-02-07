from rest_framework.views import APIView
from rest_framework.response import Response

from shared_models.models import Product, Store, Profile, Cart
from rest_framework.status import HTTP_200_OK

from cart.auth import IsAuthenticated
from cart.mixins import ResponseFormaterMixin
from decimal import Decimal

from campuslibs.cart.common import validate_membership, apply_discounts, validate_coupon

def format_payload(payload):
    # payload data format is designed insensibly.
    # here we reformat it in a more meaningful way.

    # first we separate related and non-related products
    products = [
        {
            'product_id': item['product_id'],
            'quantity': item['quantity'],
            'student_email': item['student_email'],
            'related_products': []
        } for item in payload if not item['is_related']
    ]

    related_products = [
        {
            'product_id': item['product_id'],
            'quantity': item['quantity'],
            'related_to': item['related_to'],
            'student_email': item['student_email']
        } for item in payload if item['is_related']
    ]

    for idx, product in enumerate(products):
        for related_product in related_products:
            if product['product_id'] == related_product['related_to']:
                products[idx]['related_products'].append({
                    'product_id': related_product['product_id'],
                    'quantity': related_product['quantity'],
                    'student_email': related_product['student_email']
                })
    return products


class PaymentSummary(APIView, ResponseFormaterMixin):
    http_method_names = ['head', 'get', 'post']
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        cart_id = request.data.get('cart_id', None)
        cart = None

        if cart_id:
            try:
                cart = Cart.objects.get(id=cart_id)
            except Cart.DoesNotExist:
                pass

        cart_details = request.data.get('cart_details', [])
        if not cart_details:
            return Response({'message': 'invalid cart details'}, status=HTTP_200_OK)

        purchaser = request.data.get('purchaser_info', {})

        profile = request.profile

        try:
            primary_email = purchaser['primary_email']
        except KeyError:
            pass
        else:
            try:
                profile = Profile.objects.get(primary_email=primary_email)
            except (Profile.DoesNotExist, Profile.MultipleObjectsReturned):
                pass

        try:
            store = Store.objects.get(url_slug=request.data.get('store_slug', None))
        except Store.DoesNotExist:
            return Response({'message': 'invalid store slug'}, status=HTTP_200_OK)

        coupon_code = request.data.get('coupon_code', None)

        cart_items = format_payload(cart_details)

        sub_total = Decimal('0.00')
        total_discount = Decimal('0.00')
        total_payable = sub_total - total_discount

        discounts = []
        products = []
        coupon_messages = []

        for item in cart_items:
            try:
                product = Product.objects.get(id=item['product_id'])
            except Product.DoesNotExist:
                continue

            related_products = []

            for related_item in item['related_products']:
                try:
                    related_product = Product.objects.get(id=related_item['product_id'])
                except Product.DoesNotExist:
                    continue

                related_products.append({
                    'title': related_product.title,
                    'quantity': int(related_item['quantity']),
                    'product_type': related_product.product_type,
                    'item_price': related_product.fee,
                    'price': related_product.fee * int(related_item['quantity']),
                })
                sub_total = sub_total + (related_product.fee * int(related_item['quantity']))

            products.append({
                'title': product.title,
                'quantity': int(item['quantity']),
                'product_type': product.product_type,
                'item_price': product.fee,
                'price': product.fee * int(item['quantity']),
                'related_products': related_products
            })
            sub_total = sub_total + (product.fee * int(item['quantity']))

        # sub_total updated. so update total_payable too
        total_payable = sub_total - total_discount

        # membership section
        # get the memberships this particular user bought
        membership_program = validate_membership(store, profile)
        if membership_program:
            membership_discount = apply_discounts(membership_program.discount_program)

            total_discount = total_discount + membership_discount

            discounts.append({
                'type': 'membership',
                'title': membership_program.title,
                'amount': membership_discount
            })
        # total_discount updated. so update total_payable too
        total_payable = sub_total - total_discount

        # coupon section

        # TODO: first, check if discount_program from membership and discount_program from coupon are both the same.
        # if not, only then proceed. same discount_program can only be applied once.
        if coupon_code:
            coupon, coupon_message = validate_coupon(store, coupon_code, profile)

            if coupon:
                coupon_discount = apply_discounts(coupon.discount_program)
                discounts.append({
                    'type': 'coupon',
                    'code': coupon.code,
                    'amount': coupon_discount
                })

                total_discount = total_discount + coupon_discount
                # total_discount updated. so update total_payable too
                total_payable = sub_total - total_discount
            else:
                coupon_messages.append({
                    'code': coupon_code,
                    'message': coupon_message
                })

        data = {
            'products': products,
            'discounts': discounts,
            'subtotal': sub_total,
            'total_discount': total_discount,
            'total_payable': total_payable,
            'coupon_messages': coupon_messages
        }

        return Response(self.object_decorator(data), status=HTTP_200_OK)
