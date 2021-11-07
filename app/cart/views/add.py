from campuslibs.cart.common import coupon_apply, create_cart, get_store_from_product, tax_apply
from django_scopes import scopes_disabled
from django.db.models import Sum

from rest_framework.views import APIView
from rest_framework.response import Response

from shared_models.models import Product, StoreCourseSection, StoreCertificate, StorePaymentGateway
from rest_framework.status import HTTP_200_OK

from cart.auth import IsAuthenticated
from cart.mixins import ResponseFormaterMixin
from cart.serializers import StoreSerializer


class AddToCart(APIView, ResponseFormaterMixin):
    http_method_names = ['head', 'get', 'post']
    permission_classes = (IsAuthenticated, )

    def post(self, request, *args, **kwargs):
        product_ids = request.data.get('product_ids', None)
        coupon_code = request.data.get('coupon_code', None)
        zip_code = request.data.get('zip_code', None)

        # get the products first
        products = Product.objects.filter(id__in=product_ids)
        if not products.exists():
            return Response({'message': 'product_ids must contain valid product ids'}, status=HTTP_200_OK)

        store = get_store_from_product(products)
        fee_aggregate = products.aggregate(total_amount=Sum('fee'))
        total_amount = fee_aggregate['total_amount']
        cart = create_cart(store, products, total_amount, request.profile)  # cart must belong to a profile or guest

        coupon, discount_amount, coupon_message = coupon_apply(store, coupon_code, total_amount, request.profile, cart)

        sales_tax, tax_message = tax_apply(zip_code, products, cart)

        data = format_response(store, products, cart, discount_amount, coupon_message, sales_tax, tax_message)

        return Response(self.object_decorator(data), status=HTTP_200_OK)


def format_response(store, products, cart, discount_amount, coupon_message, sales_tax, tax_message):
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
                if store_course_section.store_course.course.course_image_uri:
                    image_uri = store_course_section.store_course.course.course_image_uri.url
                else:
                    image_uri = store_course_section.store_course.course.external_image_url,

                section_data = []
                for scc in StoreCourseSection.objects.filter(store_course=store_course_section.store_course,
                                                             is_published=True):
                    section_data.append({
                        'start_date': scc.section.start_date,
                        'end_date': scc.section.end_date,
                        'execution_site': scc.section.execution_site,
                        'execution_mode': scc.section.execution_mode,
                        'name': scc.section.name,
                        'product_id': scc.product.id,
                        'price': scc.section.fee,
                        'instructor': "",  # will come from mongodb
                    })

                product_data = {
                    'id': str(product.id),
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
                        'execution_mode': store_course_section.section.execution_mode,
                        'name': store_course_section.section.name,
                        'product_id': product.id,
                        'price': product.fee,
                        'instructor': "",  # will come from mongodb
                    },
                    'sections': section_data,
                    'price': product.fee,
                    'questionnaire': []
                }

        all_items.append(product_data)

    data = {
        'discount_amount': discount_amount,
        'coupon_message': coupon_message,
        'sales_tax': sales_tax,
        'tax_message': tax_message,
        'products': all_items,
        'payment_gateways': payment_gateways,
        'cart_id': str(cart.id) if cart is not None else '',
        'store': store_serializer.data
    }
    return data
