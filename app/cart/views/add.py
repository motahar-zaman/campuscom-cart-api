from campuslibs.cart.common import coupon_apply, create_cart, get_store_from_product, tax_apply
from django_scopes import scopes_disabled
from django.db.models import Sum

from rest_framework.views import APIView
from rest_framework.response import Response

from shared_models.models import Product, StoreCourseSection, StoreCertificate, StorePaymentGateway, ProfileQuestion, \
    RegistrationQuestion, StoreCompany, RelatedProduct, PaymentQuestion
from rest_framework.status import HTTP_200_OK

from cart.auth import IsAuthenticated
from cart.mixins import ResponseFormaterMixin
from cart.serializers import StoreSerializer
from decouple import config


class AddToCart(APIView, ResponseFormaterMixin):
    http_method_names = ['head', 'get', 'post']
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        product_ids = request.data.get('product_ids', None)
        coupon_code = request.data.get('coupon_code', None)
        zip_code = request.data.get('zip_code', None)

        # get the products first
        with scopes_disabled():
            published_sections = StoreCourseSection.objects.filter(
                store_course__enrollment_ready=True,
                product__in=product_ids
            ).values('product')
            published_certificates = StoreCertificate.objects.filter(
                enrollment_ready=True,
                product__in=product_ids
            ).values('product')

        products = Product.objects.filter(id__in=published_sections.union(published_certificates))

        if not products.exists():
            return Response({'message': 'No product available'}, status=HTTP_200_OK)

        store = get_store_from_product(products)
        fee_aggregate = products.aggregate(total_amount=Sum('fee'))
        total_amount = fee_aggregate['total_amount']

        product_count = {}
        for product_id in product_ids:
            if product_id in product_count:
                product_count[product_id] = product_count[product_id] + 1
            else:
                product_count[str(product_id)] = 1

        cart = create_cart(store, products, product_count, total_amount, request.profile)  # cart must belong to a profile or guest

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
    profile_question_course_provider = ProfileQuestion.objects.none()
    profile_question_store = ProfileQuestion.objects.none()
    for product in products:
        product_data = {}

        with scopes_disabled():
            store = product.store
            course_provider = None

            # getting registration questions
            if product.product_type == 'section':
                course_provider = product.store_course_section.store_course.course.course_provider
                registration_questions = RegistrationQuestion.objects.filter(
                    entity_type='course', entity_id=product.store_course_section.store_course.course.id)
            elif product.product_type == 'certificate':
                course_provider = product.store_certificate.certificate.course_provider
                registration_questions = RegistrationQuestion.objects.filter(
                    entity_type='certificate', entity_id=product.store_certificate.certificate.id)

            # getting profile questions
            profile_question_course_provider = profile_question_course_provider.union(ProfileQuestion.objects.filter(
                provider_type='course_provider', provider_ref=course_provider.id))
            profile_question_store = profile_question_store.union(ProfileQuestion.objects.filter(provider_type='store',
                                                                                                 provider_ref=store.id))

            registration_question_list = []
            for question in registration_questions:
                question_details = {
                    "id": question.question_bank.id,
                    "type": question.question_bank.question_type,
                    "label": question.question_bank.title,
                    "display_order": question.display_order,
                    "configuration": question.question_bank.configuration
                }
                registration_question_list.append(question_details)

            try:
                store_certificate = StoreCertificate.objects.get(product=product)
            except StoreCertificate.DoesNotExist:
                pass
            else:
                if store_certificate.certificate.certificate_image_uri:
                    image_uri = config('CDN_URL') + 'uploads' + store_certificate.certificate.certificate_image_uri.url
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
                    image_uri = config('CDN_URL') + 'uploads' + store_course_section.store_course.course.course_image_uri.url
                else:
                    image_uri = store_course_section.store_course.course.external_image_url

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

                related_products = RelatedProduct.objects.filter(product=product.id)
                related_product_list = []

                for related_product in related_products:
                    image_uri = None
                    if related_product.related_product.image:
                        image_uri = config('CDN_URL') + 'uploads' + related_product.related_product.image.url

                    details = {
                        'id': str(related_product.related_product.id),
                        'title': related_product.related_product.title,
                        'image_uri': image_uri,
                        'product_type': related_product.related_product.product_type,
                        'relation_type': related_product.related_product_type,
                        'price': related_product.related_product.fee
                    }
                    related_product_list.append(details)

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

                    'registration_questions': registration_question_list,
                    'related_products': related_product_list
                }
        all_items.append(product_data)

    profile_question_list = []
    course_provider_max_order = 1
    for question in profile_question_course_provider:
        if course_provider_max_order < question.display_order:
            course_provider_max_order = question.display_order

        if question.question_bank.id not in list({questions["id"]: questions for questions in profile_question_list}):
            question_details = {
                "id": question.question_bank.id,
                "type": question.question_bank.question_type,
                "label": question.question_bank.title,
                "display_order": question.display_order,
                "configuration": question.question_bank.configuration
            }
            profile_question_list.append(question_details)

    for question in profile_question_store:
        if question.question_bank.id not in list({questions["id"]: questions for questions in profile_question_list}):
            question_details = {
                "id": question.question_bank.id,
                "type": question.question_bank.question_type,
                "label": question.question_bank.title,
                "display_order": question.display_order + course_provider_max_order,
                "configuration": question.question_bank.configuration
            }
            profile_question_list.append(question_details)

    companies = StoreCompany.objects.filter(store=store.id)
    company_list = []
    for company in companies:
        company_details = {
            "id": company.id,
            "name": company.company_name
        }
        company_list.append(company_details)

    payment_question_list = []
    payment_questions = PaymentQuestion.objects.filter(store=store.id)
    for question in payment_questions:
        question_details = {
            "id": question.question_bank.id,
            "type": question.question_bank.question_type,
            "label": question.question_bank.title,
            "display_order": question.display_order,
            "configuration": question.question_bank.configuration
        }
        payment_question_list.append(question_details)

    data = {
        'discount_amount': discount_amount,
        'coupon_message': coupon_message,
        'sales_tax': sales_tax,
        'tax_message': tax_message,
        'products': all_items,
        'payment_gateways': payment_gateways,
        'cart_id': str(cart.id) if cart is not None else '',
        'store': store_serializer.data,
        'profile_questions': profile_question_list,
        'companies': company_list,
        'payment_questions': payment_question_list
    }
    return data
