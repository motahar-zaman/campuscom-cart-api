import requests
import base64
from decimal import Decimal
from django_scopes import scopes_disabled
from django.utils import timezone
from django.db.models import Sum

from rest_framework.views import APIView
from rest_framework.response import Response

from shared_models.models import (
    Cart, StorePaymentGateway, Product, CartItem, Coupon, CertificateEnrollment,
    CourseEnrollment, Country, StoreCourseSection, StoreCertificate
)
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST

from cart.auth import IsAuthenticated
from cart.mixins import ResponseFormaterMixin
# from cart.tasks import generic_task_enqueue

from cart.utils import get_store_from_product, is_already_enrolled, get_formatted_data_and_price
from cart.serializers import StoreSerializer
from decouple import config


class AddToCart(APIView, ResponseFormaterMixin):
    http_method_names = ['head', 'get', 'post']
    permission_classes = (IsAuthenticated, )

    def post(self, request, *args, **kwargs):
        product_ids = request.data.get('product_ids', None)
        coupon_code = request.data.get('coupon_code', None)
        zip_code = request.data.get('zip_code', None)
        persistent = request.data.get('persistent', None)

        # the permission class IsAuthenticated handles checkout=guest.
        # checkout = request.data.get('checkout', None)

        # get the products first

        products = Product.objects.filter(id__in=product_ids)
        if not products.exists():
            return Response({'message': 'product_ids must contain valid product ids'}, status=HTTP_200_OK)

        fee_aggregate = products.aggregate(total_amount=Sum('fee'))
        total_amount = fee_aggregate['total_amount']

        cart = create_cart(products, total_amount, request.profile, persistent)  # cart must belong to a profile or guest

        coupon, discount_amount, coupon_message = coupon_apply(products, coupon_code, total_amount, request.profile, cart)

        if zip_code is not None and cart.store.tax_enabled:
            sales_tax, tax_id = tax_apply(zip_code, products, cart)

        data = format_response(products, cart)

        return Response(self.object_decorator(data), status=HTTP_200_OK)


def format_response(products, cart):
    products = get_formatted_data_and_price(products)
    store = get_store_from_product(products)
    store_serializer = StoreSerializer(store)

    payment_gateways = []
    for item in StorePaymentGateway.objects.filter(store__url_slug=store.url_slug):
        payment_gateways.append({
            'id': str(item.id),
            'name': item.payment_gateway.name,
            'branding': item.branding
        })

    data = {
        'product': products,
        'payment_gateways': payment_gateways,
        'cart_id': str(cart.id) if cart is not None else '',
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
    return data


def create_cart(products, total_amount, profile, persistent):
    if persistent is None:
        return None
    # the values set here will be updated twice:
    # 1. once coupon is applied
    # 2. once tax is applied
    store = get_store_from_product(products)

    with scopes_disabled():
        cart = Cart.objects.create(
            profile=profile,
            store=store,
            coupon=None,
            status=Cart.STATUS_OPEN,
            extended_amount=total_amount,
            discount_amount=Decimal('0.00'),
            sales_tax=Decimal('0.00'),
            total_amount=total_amount,
            note='',
        )

    # iterate products and create items
    # quantity will be number of products
    for product in products:
        CartItem.objects.create(
            quantity=1,
            unit_price=product.fee,
            extended_amount=product.fee,
            discount_amount=Decimal('0.0'),
            sales_tax=Decimal('0.0'),
            total_amount=product.fee
        )
    return cart


def coupon_apply(products, coupon_code, total_amount, profile, cart):
    # see if this coupon is fine or not
    price_before_discount = total_amount
    discount = Decimal('0.0')

    if coupon_code is None:
        return None, discount, 'no coupon applied'

    # applying coupon
    try:
        coupon = Coupon.objects.get(store=cart.store, code=coupon_code)
    except Coupon.DoesNotExist:
        return None, discount, 'no coupon found with that code'

    today = timezone.now()
    if not coupon.is_active:
        return coupon, discount, 'coupon is not active anymore'

    if today < coupon.start_date:
        return coupon, discount, 'coupon from future is not supported'

    if today > coupon.end_date:
        return coupon, discount, 'coupon already expired'

    if profile is not None:
        if CertificateEnrollment.objects.filter(profile=profile, cart_item__cart__coupon=coupon).exists() or \
                CourseEnrollment.objects.filter(profile=profile, cart_item__cart__coupon=coupon).exists():
            return coupon, discount, 'this coupon has already been used'

    if coupon.amount < 0.00:
        coupon.amount = Decimal('0.00')

    if coupon.coupon_type == 'fixed':
        # coupon.max_limit makes little sense here
        discount = coupon.amount

    else:
        # if coupon_type is not fixed, then it must be a percentage
        # coupon.max_limit makes sense here

        discount = total_amount * coupon.amount / 100

        if coupon.max_limit is not None and discount > coupon.max_limit:
            discount = coupon.max_limit

    price = total_amount - discount

    if price < 0.00:
        price = Decimal('0.00')
        discount = price_before_discount

    if cart is not None:
        cart.coupon = coupon
        cart.discount = discount
        cart.total_amount = price
        cart.save()

        # now should we iterate over all cart item and apply the same discount to all the items???

    return coupon, discount, 'coupon applied successfully'


def tax_apply(zip_code, products, cart):
    # this whole thing has to be redone. because avatax allows calculating multiple products tax in just one request.
    # so instead of iterating products, we should use that instead

    accountid = config('AVATAX_ACCOUNT_ID')
    license_key = config('AVATAX_LICENSE_KEY')
    company_code = config('AVATAX_COMPANY_CODE')

    cart_item = cart.cart_items.first()  # since all carts will only have one item, at least for now

    country, created = Country.objects.get_or_create(name='United States')

    if product.tax_code is None:
        tax_code = config('AVATAX_TAX_CODE')

    auth_str = base64.b64encode(f'{accountid}:{license_key}'.encode('ascii')).decode('ascii')
    auth_header = {'Authorization': f'Basic {auth_str}'}
    url = config('AVATAX_URL')
    description = ''

    try:
        store_course_section = StoreCourseSection.objects.get(product=product)
        description = store_course_section.store_course.course.title + \
            ' (' + store_course_section.store_course.course.course_provider.name + ')'
    except StoreCourseSection.DoesNotExist:
        pass

    try:
        store_certificate = StoreCertificate.objects.get(product=product)
        description = store_certificate.certificate.title + ' (' + store_certificate.certificate.course_provider.name + ')'
    except StoreCertificate.DoesNotExist:
        pass

    data = {
        'addresses': {
            'shipTo': {
                'country': country,
                'postalCode': zip_code
            },
            'shipFrom': {
                'country': country,
                'postalCode': '02199'
            }
        },
        'type': 'SalesOrder',
        'companyCode': company_code,
        'date': timezone.now().strftime("%Y-%m-%d"),
        'customerCode': 'avatax@campus.com',
        'lines': [
            {
                'number': 1,
                'amount': cart.total_amount,
                'taxCode': tax_code,
                'description': description
            }
        ]
    }

    resp = requests.post(url, json=data, headers=auth_header)

    resp_json = resp.json()

    if resp.status_code == 201:
        try:
            return {'total_amount': resp_json['totalTax']}
        except KeyError:
            pass

    return Decimal('0.0')
