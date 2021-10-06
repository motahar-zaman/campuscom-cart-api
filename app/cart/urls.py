from django.urls import path
from rest_framework import routers
from cart.views import AddToCart, coupon_validate, CartDetails, tax

router = routers.DefaultRouter()


urlpatterns = [
    path('cart/', AddToCart.as_view(), name='add_to_cart'),
    path('cart-details/', CartDetails.as_view(), name='cart_details'),
    path('coupon-validate/', coupon_validate, name='coupon_validate'),
    path('tax/', tax, name='tax'),
]
