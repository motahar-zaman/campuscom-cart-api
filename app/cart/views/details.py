from django_scopes import scopes_disabled

from rest_framework.views import APIView
from rest_framework.response import Response

from cart.mixins import ResponseFormaterMixin


class CartDetails(APIView, ResponseFormaterMixin):
    http_method_names = ['head', 'get']

    def get(self, request, *args, **kwargs):
        cart_id = self.request.query_params.get('cart_id', None)

        with scopes_disabled():
            try:
                cart = Cart.objects.get(id=cart_id)
            except Cart.DoesNotExist:
                return Response({'message': 'Cart does not exist'}, status=HTTP_400_BAD_REQUEST)

        products = []

        for cart_item in cart.cart_items.all():
            product = cart_item.product
            sections = []

            try:
                store_course_section = StoreCourseSection.objects.get(product=product)
                item = store_course_section.store_course.course

                for section in item.sections.all():
                    sections.append({
                        'code': section.name
                    })

                products.append({
                    'id': str(product.id),
                    'title': item.title,
                    'slug': item.slug,
                    'provider': {'code': item.course_provider.code},
                    'product_type': 'store_course_section',
                    'sections': sections
                })
            except StoreCourseSection.DoesNotExist:
                try:
                    store_certificate = StoreCertificate.objects.get(product=product)
                    item = store_certificate.certificate

                    products.append({
                        'id': str(product.id),
                        'title': item.title,
                        'slug': item.slug,
                        'provider': {'code': item.course_provider.code},
                        'product_type': 'certificate',
                        'sections': sections
                    })
                except StoreCertificate.DoesNotExist:
                    return Response(self.object_decorator({}), status=HTTP_200_OK)

        data = {
            'cart_id': str(cart.id),
            'status': cart.status,
            'products': products
        }

        return Response(self.object_decorator(data), status=HTTP_200_OK)
