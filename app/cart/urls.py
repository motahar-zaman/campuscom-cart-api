from django.urls import path
from rest_framework import routers
from cart.views import AddToCart, CartDetails

router = routers.DefaultRouter()


urlpatterns = [
    path('cart/', AddToCart.as_view(), name='add_to_cart'),
    path('cart-details/', CartDetails.as_view(), name='cart_details')
]
