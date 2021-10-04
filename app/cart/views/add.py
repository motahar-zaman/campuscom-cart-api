from decimal import Decimal
from django.views.decorators.csrf import csrf_exempt
from django_scopes import scopes_disabled

from rest_framework.views import APIView
from rest_framework.response import Response

from shared_models.models import Cart, StorePaymentGateway

from rest_framework.status import HTTP_200_OK

from cart.auth import IsAuthenticated
from cart.mixins import ResponseFormaterMixin
from rest_framework.decorators import api_view, permission_classes
from cart.tasks import generic_task_enqueue


class AddToCart(APIView, ResponseFormaterMixin):
    http_method_names = ['head', 'get', 'delete']
    permission_classes = (IsAuthenticated, )

    def get(self, request, *args, **kwargs):
        product_id = self.request.query_params.get('product_id', None)
        cart_id = self.request.query_params.get('cart_id', None)

        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Response({'message': 'Product does not exist'}, status=HTTP_400_BAD_REQUEST)

        if request.profile is not None:
            if is_already_enrolled(product, request.profile):
                return Response({'message': 'Already enrolled in this course or certificate'}, status=HTTP_400_BAD_REQUEST)

        try:
            store = product.store_course_section.store_course.store
        except StoreCourseSection.DoesNotExist:
            store = product.store_certificate.store

        if cart_id:
            with scopes_disabled():
                try:
                    cart = Cart.objects.get(id=cart_id)
                    cart.coupon = None
                except Cart.DoesNotExist:
                    return Response({'message': 'Cart does not exist'}, status=HTTP_400_BAD_REQUEST)
        else:
            # total_amount and extended_amount is zero because we don't know the value here, since the value will come from cart_item
            with scopes_disabled():
                cart = Cart.objects.create(
                    profile=request.profile,
                    store=store,
                    coupon=None,
                    status=Cart.STATUS_OPEN,
                    extended_amount=Decimal('0.00'),
                    discount_amount=Decimal('0.00'),
                    sales_tax=Decimal('0.00'),
                    total_amount=Decimal('0.00'),
                    note='initiated by user in consumer api',
                )

        quantity = 1
        discount_amount = Decimal('0.00')
        sales_tax_amount = Decimal('0.00')

        unit_price, product_data = get_formatted_data_and_price(product)
        total_amount = unit_price * quantity
        extended_amount = total_amount - discount_amount + sales_tax_amount

        # multiple items in a cart is not supported yet. so we take the first.
        # when it will be supported, we will just create new cart item.

        if cart.cart_items.exists():
            cart_item = cart.cart_items.first()
        else:
            cart_item = CartItem.objects.create(
                cart=cart,
                product=product,
                quantity=quantity,
                unit_price=unit_price,
                extended_amount=extended_amount,
                discount_amount=discount_amount,
                sales_tax=sales_tax_amount,
                total_amount=total_amount,
            )

        # now update the barren cart object with these values

        # total_amount will be the sum of all cart_item's total amounts. however,
        # right now only one cart item is supported. therefore, we could just use cart.total_amount = cart_item.total_amount amount.
        # but we instead increment, hoping in future it will be useful.
        cart.total_amount = cart.total_amount + cart_item.total_amount
        cart.extended_amount = cart.extended_amount + cart_item.extended_amount
        cart.save()

        # other fields e.g. discount_amount and salex_tax will be set in respective places. here it's just 0.00

        store_serializer = StoreSerializer(store)

        payment_gateways = []
        for item in StorePaymentGateway.objects.filter(store__url_slug=store.url_slug):
            payment_gateways.append({
                'id': str(item.id),
                'name': item.payment_gateway.name,
                'branding': item.branding
            })

        return payment_gateways

        data = {
            'product': product_data,
            'payment_gateways': payment_gateways,
            'cart_id': str(cart.id),
            'store': store_serializer.data,
            'questionnaire': [
                {
                    'type': 'checkbox',
                    'field': 'have_relevant_certificate',
                    'label': 'Do you have a relevant certificate?'
                },
                {
                    'type': 'text',
                    'field': 'certificate_number',
                    'label': 'Enter the certificate number'
                },
                {
                    'type': 'date',
                    'field': 'certificate_expiry_date',
                    'label': 'Certificate expiry date'
                }
            ]
        }

        if cart.profile is not None:  # can not update crm if there is no zipcode
            generic_task_enqueue('crm_product.enroll', cart_id=str(cart.id), store_id=str(cart.store.id))

        return Response(self.object_decorator(data), status=HTTP_200_OK)

    def delete(self, request, *args, **kwargs):
        try:
            cart_id = request.data['cart_id']
        except KeyError:
            return Response({'message': 'Invalid cart id'}, status=HTTP_400_BAD_REQUEST)

        with scopes_disabled():
            try:
                cart = Cart.objects.get(id=cart_id)
            except Cart.DoesNotExist:
                return Response({'message': 'Cart does not exist'}, status=HTTP_400_BAD_REQUEST)

        cart.status = 'cancelled'
        cart.save()

        return Response(self.object_decorator({'message': 'Cart status set to cancelled'}), status=HTTP_200_OK)


@api_view(http_method_names=['POST'])
def coupon_validate(request):
    request_data = request.data.copy()
    coupon_code = request_data.get('coupon_code', None)
    if coupon_code is not None:
        coupon_code = coupon_code.strip()
    store_slug = request_data.get('store_slug', None)
    cart_id = request_data.get('cart_id', None)

    with scopes_disabled():
        try:
            cart = Cart.objects.get(id=cart_id)
        except Cart.DoesNotExist:
            return Response({'message': 'Cart not found'}, status=HTTP_400_BAD_REQUEST)

    try:
        store = Store.objects.get(url_slug=store_slug)
    except Store.DoesNotExist:
        return Response({'message': 'Store not found'}, status=HTTP_400_BAD_REQUEST)

    try:
        coupon = Coupon.objects.get(store=store, code=coupon_code)
    except Coupon.DoesNotExist:
        return Response({'message': 'Coupon not found'}, status=HTTP_400_BAD_REQUEST)

    validate_coupon(coupon)

    dicounted_price, discount_amount = apply_coupon(cart.extended_amount, coupon)

    cart.coupon = coupon
    cart.discount_amount = discount_amount
    cart.total_amount = cart.extended_amount - discount_amount
    cart.save()

    # now, here we should also set these values for cart_item. let's try here. but doesn't feel dandy.

    cart_item = cart.cart_items.first()  # since cart doesn't support multiple items yet
    cart_item.discount_amount = discount_amount
    cart_item.total_amount = cart_item.extended_amount - discount_amount
    cart_item.save()

    data = {
        'discounted_price': dicounted_price,
        'discount': discount_amount
    }
    return Response(data, status=HTTP_201_CREATED)


@api_view(http_method_names=['POST'])
@csrf_exempt
def tax(request):
    request_data = request.data.copy()
    zip_code = request_data.get('zip_code', None)
    country = request_data.get('country', None)
    cart_id = request_data.get('cart_id', None)

    with scopes_disabled():
        try:
            cart = Cart.objects.get(id=cart_id)
        except Cart.DoesNotExist:
            return Response({'message': 'Cart not found'}, status=HTTP_400_BAD_REQUEST)

    # cart just has only one item. so getting the product is simple.
    if cart.cart_items.exists():
        cart_item = cart.cart_items.first()
    else:
        return Response({'message': 'Cart item not found'}, status=HTTP_400_BAD_REQUEST)

    product = cart_item.product

    if zip_code is None or country is None:
        return Response({'message': 'zip_code and country both must be provided'}, status=HTTP_400_BAD_REQUEST)

    # country model does not have a country code field. but frontend is going to send country code? this is awkward.
    # country, created = Country.objects.get_or_create(name='United States')

    tax_info = get_tax_info(zip_code, country, cart, product)

    try:
        tax_amount = tax_info['total_amount']
    except KeyError:
        return Response({'message': 'Could not retrieve tax info. Is the provided address correct?'}, status=HTTP_400_BAD_REQUEST)

    cart.sales_tax = tax_amount
    cart_item.sales_tax = tax_amount

    cart.total_amount = cart.total_amount + Decimal(tax_amount)
    cart_item.total_amount = cart.total_amount + Decimal(tax_amount)

    cart.save()
    cart_item.save()

    return Response(tax_info, status=HTTP_200_OK)
