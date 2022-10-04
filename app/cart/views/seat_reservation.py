from rest_framework.views import APIView
from rest_framework.response import Response

from shared_models.models import Product, StoreCourseSection, StoreCertificate, Store, MembershipProgram, Profile

from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND

from cart.auth import IsAuthenticated
from cart.mixins import ResponseFormaterMixin, JWTMixin
from campuslibs.seat_reservation.registration import Registration


class SeatRegistrationDetailsView(APIView, JWTMixin, ResponseFormaterMixin):
    permission_classes = (IsAuthenticated,)
    http_method_names = ["head", "post"]

    def post(self, request, *args, **kwargs):
        reservation_token = request.data.get('reservation_token', None)

        if reservation_token:
            seat_registration = Registration()
            status, message, processed_data = seat_registration.registration_details(reservation_token)
        if not status:
            return Response({'message': message}, status=HTTP_200_OK)

        return Response(self.object_decorator(processed_data), status=HTTP_200_OK)
