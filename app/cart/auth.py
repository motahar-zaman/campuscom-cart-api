from shared_models.models.registration import Profile
from rest_framework.permissions import IsAuthenticated, SAFE_METHODS
from decouple import config
import jwt
from rest_framework.exceptions import AuthenticationFailed


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
                raise AuthenticationFailed()
            except Exception as e:
                print(e)
                raise AuthenticationFailed()

            try:
                request.profile = Profile.objects.get(id=data['id'])
            except Profile.DoesNotExist:
                raise AuthenticationFailed()
            return True
        raise AuthenticationFailed()

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.id == request.profile
