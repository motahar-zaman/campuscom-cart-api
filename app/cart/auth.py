from shared_models.models.registration import Profile
from rest_framework.permissions import IsAuthenticated, SAFE_METHODS
from decouple import config
import jwt

# from rest_framework.exceptions import APIException
# from rest_framework import status


# class ProfileCredentialException(APIException):
#     status_code = status.HTTP_401_UNAUTHORIZED
#     default_error = 'invalid_client'
#     default_detail = 'Profile credentials were not found in the headers or body'


class IsAuthenticated(IsAuthenticated):

    def has_permission(self, request, view):
        checkout = request.query_params.get('checkout', 'nada')
        if checkout == 'guest':
            request.profile = None
            return True  # if checkout is guest, then no auth is required. profile will be none. cart will accept this gracefully.

        if 'access_token' in request.COOKIES:
            access_token = request.COOKIES['access_token']
            try:
                data = jwt.decode(str(access_token), config('ACCESS_TOKEN_SECRET'), algorithms=config('JWT_ALGORITHM'))
            except jwt.ExpiredSignatureError:
                print('sig expired')
                # raise appropriate exceptions
            except Exception as e:
                # raise appropriate exceptions
                print(e)
                # raise InvalidProfileCredentialsException()

            try:
                request.profile = Profile.objects.get(id=data['id'])
            except Profile.DoesNotExist:
                # raise invalid cred
                print('profile not found')
            return True
        # raise ProfileCredentialsRequiredException()
        print('no access token in cookies found')

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.id == request.profile
