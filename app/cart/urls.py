from django.urls import path
from rest_framework import routers
from cart.views import AddToCart, CartDetails, PaymentSummary, health_check, SeatRegistrationDetailsView

router = routers.DefaultRouter()


urlpatterns = [
    path('cart/', AddToCart.as_view(), name='add_to_cart'),
    path('cart-details/', CartDetails.as_view(), name='cart_details'),
    path('payment-summary/', PaymentSummary.as_view(), name='payment_summary'),
    path('check/', health_check),

    # reservation seat registration
    path('seat-registration-details/', SeatRegistrationDetailsView.as_view(), name='seat_registration_details'),
]
