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
from rest_framework.status import HTTP_200_OK

from cart.auth import IsAuthenticated
from cart.mixins import ResponseFormaterMixin
# from cart.tasks import generic_task_enqueue

from cart.utils import get_store_from_product, is_already_enrolled
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

        coupon, discount_amount, coupon_message = coupon_apply(coupon_code, total_amount, request.profile, cart)

        sales_tax, tax_message = tax_apply(zip_code, products, cart)

        data = format_response(products, cart, coupon_message, tax_message)

        return Response(self.object_decorator(data), status=HTTP_200_OK)


def create_cart(products, total_amount, profile, persistent):
    if persistent is not True:
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
            # before adding a product to a cart, we should check if user is already enrolled in this or not.
            # if yes, we should skip?
            if not is_already_enrolled(product, profile):
                CartItem.objects.create(
                    cart=cart,
                    product=product,
                    quantity=1,
                    unit_price=product.fee,
                    extended_amount=product.fee,
                    discount_amount=Decimal('0.0'),
                    sales_tax=Decimal('0.0'),
                    total_amount=product.fee
                )
    return cart


def get_discounts(coupon, total_amount):
    price_before_discount = total_amount

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

    return price, discount


def coupon_apply(coupon_code, total_amount, profile, cart):
    # see if this coupon is fine or not
    discount = Decimal('0.0')

    if coupon_code is None:
        return None, discount, 'no coupon applied'

    # applying coupon
    with scopes_disabled():
        try:
            coupon = Coupon.objects.get(code=coupon_code)
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

    price, discount = get_discounts(coupon, total_amount)

    if cart is not None:
        cart.coupon = coupon
        cart.extended_amount = price
        cart.discount_amount = discount
        cart.save()

        # now should we iterate over all cart item and apply the same discount to all the items?
        # yes we should

        for item in cart.cart_items.all():
            price, discount = get_discounts(coupon, item.unit_price)
            item.extended_amount = price
            item.discount_amount = discount
            item.save()

    return coupon, discount, 'coupon applied successfully'


def tax_apply(zip_code, products, cart):
    sales_tax = Decimal('0.0')
    store = get_store_from_product(products)

    if zip_code is None or store.tax_enabled is False:
        return sales_tax, 'tax disabled'

    accountid = config('AVATAX_ACCOUNT_ID')
    license_key = config('AVATAX_LICENSE_KEY')
    company_code = config('AVATAX_COMPANY_CODE')
    url = config('AVATAX_URL')

    lines = []

    for idx, product in enumerate(products):
        tax_code = product.tax_code
        if product.tax_code is None:
            tax_code = config('AVATAX_TAX_CODE')

        with scopes_disabled():
            try:
                store_course_section = StoreCourseSection.objects.get(product=product)
                description = store_course_section.store_course.course.title + \
                    ' (' + store_course_section.store_course.course.course_provider.name + ')'
            except StoreCourseSection.DoesNotExist:
                pass

            try:
                store_certificate = StoreCertificate.objects.get(product=product)
                description = store_certificate.certificate.title + \
                    ' (' + store_certificate.certificate.course_provider.name + ')'
            except StoreCertificate.DoesNotExist:
                pass

        if cart is None:
            amount = product.fee
        else:
            cart_item = cart.cart_items.get(product=product)
            amount = cart_item.extended_amount

        lines.append({
            'number': idx,
            'amount': str(amount),
            'taxCode': tax_code,
            'description': description
        })

    country, created = Country.objects.get_or_create(name='United States')

    data = {
        'addresses': {
            'shipTo': {
                'country': 'US',
                'postalCode': zip_code
            },
            'shipFrom': {
                'country': 'US',
                'postalCode': '02199'
            }
        },
        'type': 'SalesOrder',
        'companyCode': company_code,
        'date': timezone.now().strftime("%Y-%m-%d"),
        'customerCode': 'avatax@campus.com',
        'lines': lines
    }

    auth_str = base64.b64encode(f'{accountid}:{license_key}'.encode('ascii')).decode('ascii')
    auth_header = {'Authorization': f'Basic {auth_str}'}

    resp = requests.post(url, json=data, headers=auth_header)
    resp_json = resp.json()

    if resp.status_code == 201:
        try:
            sales_tax = Decimal(resp_json['totalTax'])
        except KeyError:
            sales_tax = Decimal('0.0')

    if cart is not None:
        cart.sales_tax = sales_tax
        cart.extended_amount = cart.extended_amount + sales_tax
        cart.save()

        for idx, product in enumerate(products):
            line = resp_json['lines'][idx]
            item = cart.cart_items.get(product=product)
            item.extended_amount = item.extended_amount - Decimal(line['taxableAmount'])
            item.sales_tax = Decimal(line['taxableAmount'])
            item.save()

    # now, should we iterate over the cart items and change the values there too?
    # yes we should

    return sales_tax, 'tax applied successfully'


def format_response(products, cart, coupon_message, tax_message):
    store = get_store_from_product(products)
    store_serializer = StoreSerializer(store)

    payment_gateways = []
    for item in StorePaymentGateway.objects.filter(store__url_slug=store.url_slug):
        payment_gateways.append({
            'id': str(item.id),
            'name': item.payment_gateway.name,
            'branding': item.branding
        })

    all_items = []
    for product in products:
        product_data = {}

        with scopes_disabled():
            try:
                store_certificate = StoreCertificate.objects.get(product=product)
            except StoreCertificate.DoesNotExist:
                pass
            else:
                image_uri = ''

                if store_certificate.certificate.certificate_image_uri:
                    image_uri = store_certificate.certificate.certificate_image_uri.url
                else:
                    image_uri = store_certificate.certificate.external_image_url

                product_data = {
                    'id': str(store_certificate.certificate.id),
                    'title': store_certificate.certificate.title,
                    'slug': store_certificate.certificate.slug,
                    'image_uri': image_uri,
                    'external_image_url': store_certificate.certificate.external_image_url,
                    'provider': {
                        'id': store_certificate.certificate.course_provider.content_db_reference,
                        'code': store_certificate.certificate.course_provider.code
                    },
                    'price': product.fee,
                    'product_type': 'certificate'
                }

            try:
                store_course_section = StoreCourseSection.objects.get(product=product)
            except StoreCourseSection.DoesNotExist:
                pass
            else:
                image_uri = ''

                if store_course_section.store_course.course.course_image_uri:
                    image_uri = store_course_section.store_course.course.course_image_uri.url
                else:
                    image_uri = store_course_section.store_course.course.external_image_url,

                product_data = {
                    'id': store_course_section.store_course.course.id,
                    'title': store_course_section.store_course.course.title,
                    'slug': store_course_section.store_course.course.slug,
                    'image_uri': image_uri,
                    'external_image_url': store_course_section.store_course.course.external_image_url,
                    'provider': {
                        'id': store_course_section.store_course.course.course_provider.content_db_reference,
                        'code': store_course_section.store_course.course.course_provider.code
                    },
                    'product_type': 'store_course_section',
                    'section': {
                        'start_date': store_course_section.section.start_date,
                        'end_date': store_course_section.section.end_date,
                        'execution_site': store_course_section.section.execution_site,
                        'execution_mode': store_course_section.section.execution_mode
                    },
                    'price': product.fee,
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

        all_items.append(product_data)

    data = {
        'coupon_message': coupon_message,
        'tax_message': tax_message,
        'product': all_items,
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
