import requests
import base64
from decimal import Decimal
from django_scopes import scopes_disabled
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response

from shared_models.models import (
    Cart, StorePaymentGateway, Product, CartItem, Coupon, CertificateEnrollment,
    CourseEnrollment, Country, StoreCourseSection, StoreCertificate
)
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST

from cart.auth import IsAuthenticated
from cart.mixins import ResponseFormaterMixin
from cart.tasks import generic_task_enqueue

from cart.utils import get_store_from_product, is_already_enrolled, get_formatted_data_and_price
from cart.serializers import StoreSerializer
from decouple import config


class AddToCart(APIView, ResponseFormaterMixin):
    http_method_names = ['head', 'get', 'post']
    permission_classes = (IsAuthenticated, )

    def post(self, request, *args, **kwargs):
        cart_id = request.data.get('cart_id', None)
        product_id = request.data.get('product_id', None)
        coupon_code = request.data.get('coupon_code', None)
        zip_code = request.data.get('zip_code', None)

        # the permission class IsAuthenticated handles checkout=guest.
        # checkout = request.data.get('checkout', None)

        #############################################################
        # create cart block
        #############################################################

        if cart_id is None and product_id is None:
            return Response({'message': 'cart id or product id must be provided'}, status=HTTP_200_OK)

        # variable initialization
        quantity = 1
        discount_amount = Decimal('0.00')
        sales_tax = Decimal('0.00')
        tax_id = None

        with scopes_disabled():
            if cart_id is None:
                try:
                    product = Product.objects.get(id=product_id)
                except Product.DoesNotExist:
                    return Response({'message': 'Invalid product id'}, status=HTTP_400_BAD_REQUEST)

                # before proceeding further, check the availability of current product for the current profile.
                # if the profile is None e.g. guest, then the product is always available
                if is_already_enrolled(product, request.profile):
                    return Response({'message': 'Already enrolled in this course or certificate'}, status=HTTP_400_BAD_REQUEST)

                store = get_store_from_product(product)

                cart = Cart.objects.create(
                    profile=request.profile,
                    store=store,
                    coupon=None,
                    status=Cart.STATUS_OPEN,
                    note=None,
                    extended_amount=product.fee,
                    discount_amount=discount_amount,
                    sales_tax=sales_tax,
                    total_amount=product.fee,
                    tax_id=tax_id,
                    registration_details={},
                    agreement_details={}
                )

                cart_id = cart.id

            try:
                cart = Cart.objects.get(id=cart_id)
            except Cart.DoesNotExist:
                return Response({'message': 'Invalid cart id'}, status=HTTP_400_BAD_REQUEST)

                unit_price, product_data = get_formatted_data_and_price(product)
                total_amount = unit_price * quantity

                # applying coupon
                try:
                    coupon = Coupon.objects.get(store=cart.store, code=coupon_code)
                    discount_amount, coupon_message = coupon_apply(coupon, cart, request.profile)
                except Coupon.DoesNotExist:
                    coupon = None
                    coupon_message = 'coupon does not exist'

                # apply tax
                if zip_code is not None and cart.store.tax_enabled:
                    sales_tax, tax_message, tax_id = tax_apply(zip_code, cart, product)

                # calculating extended amount after getting tax and discount amounts
                extended_amount = total_amount - discount_amount + sales_tax

                # multiple items in a cart is not supported yet. so we take the first.
                # when it will be supported, we will just create new cart item.

                if cart.cart_items.exists():
                    cart_item = cart.cart_items.first()
                    cart_item.quantity = quantity
                    cart_item.unit_price = unit_price
                    cart_item.extended_amount = extended_amount
                    cart_item.discount_amount = discount_amount
                    cart_item.sales_tax = sales_tax
                    cart_item.total_amount = total_amount
                    cart_item.save()
                else:
                    cart_item = CartItem.objects.create(
                        cart=cart,
                        product=product,
                        quantity=quantity,
                        unit_price=unit_price,
                        extended_amount=extended_amount,
                        discount_amount=discount_amount,
                        sales_tax=sales_tax,
                        total_amount=total_amount,
                    )

                # now update the barren cart object with these values

                # total_amount will be the sum of all cart_item's total amounts. however,
                # right now only one cart item is supported. therefore, we can just use cart.total_amount = cart_item.total_amount amount.
                cart.coupon = coupon
                cart.total_amount = cart_item.total_amount
                cart.extended_amount = extended_amount
                cart.discount_amount = discount_amount
                cart.sales_tax = sales_tax
                cart.tax_id = tax_id
                cart.save()

                # other fields e.g. discount_amount and salex_tax will be set in appropriate places. here it's just 0.00

                store_serializer = StoreSerializer(store)

                payment_gateways = []
                for item in StorePaymentGateway.objects.filter(store__url_slug=store.url_slug):
                    payment_gateways.append({
                        'id': str(item.id),
                        'name': item.payment_gateway.name,
                        'branding': item.branding
                    })

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


def coupon_apply(coupon, cart, profile):
    # see if this coupon is fine or not

    today = timezone.now()
    if not coupon.is_active:
        return Response({'message': 'inactive coupon'}, status=HTTP_200_OK)

    if today < coupon.start_date:
        return Response({'message': 'coupon from future are not supported'}, status=HTTP_200_OK)

    if today > coupon.end_date:
        return Response({'message': 'coupon expired'}, status=HTTP_200_OK)

    if profile is not None:
        if CertificateEnrollment.objects.filter(profile=profile, cart_item__cart__coupon=coupon).exists() or \
                CourseEnrollment.objects.filter(profile=profile, cart_item__cart__coupon=coupon).exists():
            return Response({'message': 'this coupon has already been used'}, status=HTTP_200_OK)

    if coupon.amount < 0.00:
        coupon.amount = Decimal('0.00')

    price_before_discount = cart.extended_amount
    discount = Decimal('0.0')

    if coupon.coupon_type == 'fixed':
        # coupon.max_limit makes little sense here
        discount = coupon.amount

    else:
        # if coupon_type is not fixed, then it must be a percentage
        # coupon.max_limit makes sense here

        discount = cart.extended_amount * coupon.amount / 100

        if coupon.max_limit is not None and discount > coupon.max_limit:
            discount = coupon.max_limit

    price = cart.extended_amount - discount

    if price < 0.00:
        price = Decimal('0.00')
        discount = price_before_discount

    cart.coupon = coupon
    cart.discount = discount
    cart.total_amount = price
    cart.save()

    # now, here we should also set these values for cart_item. let's try here. but doesn't feel dandy.

    cart_item = cart.cart_items.first()  # since cart doesn't support multiple items yet
    cart_item.discount = discount
    cart_item.total_amount = price
    cart_item.save()

    data = {
        'discounted_price': price,
        'discount': discount
    }

    return Response(data, status=HTTP_400_BAD_REQUEST)


def tax_apply(zip_code, cart, product):
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
            tax_info = {'total_amount': resp_json['totalTax']}
        except KeyError:
            return Response({'message': 'could not collect tax info'}, status=HTTP_400_BAD_REQUEST)

    try:
        tax_amount = tax_info['total_amount']
    except KeyError:
        return Response({'message': 'Could not retrieve tax info. Is the provided address correct?'}, status=HTTP_400_BAD_REQUEST)

    return Response(tax_info, status=HTTP_200_OK)
