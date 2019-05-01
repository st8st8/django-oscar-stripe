import stripe
from django.conf import settings
from django.http import HttpResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from oscar.core.exceptions import ModuleNotFoundError
from oscar.core.loading import get_class, get_model

from oscar.apps.checkout.views import PaymentDetailsView as CorePaymentDetailsView
from oscar.apps.checkout.views import ThankYouView as CoreThankYouView

from apps.checkout import mixins
from oscar_stripe_sca.facade import Facade

from . import PAYMENT_METHOD_STRIPE, PAYMENT_EVENT_PURCHASE, STRIPE_EMAIL, STRIPE_TOKEN, STRIPE_SEND_RECEIPT

from . import forms

SourceType = get_model('payment', 'SourceType')
Source = get_model('payment', 'Source')
Line = get_model('basket', 'Line')
Selector = get_class('partner.strategy', 'Selector')
try:
    Applicator = get_class('offer.applicator', 'Applicator')
except ModuleNotFoundError:
    # fallback for django-oscar<=1.1
    Applicator = get_class('offer.utils', 'Applicator')


class PaymentDetailsView(CorePaymentDetailsView, mixins.CoracleShopOrderPlacementMixin):
    template_name = "checkout/stripe_payment_details.html"
    template_name_preview = 'checkout/stripe_preview.html'

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super(PaymentDetailsView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        self.request.session["myc_myself_option"] = "myself"
        ctx = super(PaymentDetailsView, self).get_context_data(**kwargs)

        if self.preview:
            ctx['order_total_incl_tax_cents'] = (
                ctx['order_total'].incl_tax * 100
            ).to_integral_value()
        else:
            stripe_session = Facade().begin(
                ctx["basket"],
                ctx["order_total"])
            self.request.session["stripe_session_id"] = stripe_session.id
            self.request.session["stripe_payment_intent_id"] = stripe_session.payment_intent
            ctx['stripe_publishable_key'] = settings.STRIPE_PUBLISHABLE_KEY
            ctx['stripe_session_id'] = stripe_session.id
        return ctx

    def handle_payment(self, order_number, order_total, **kwargs):
        pi = self.request.session["stripe_payment_intent_id"]
        intent = Facade().retrieve_payment_intent(pi)
        intent.capture()

        source_type, __ = SourceType.objects.get_or_create(name=PAYMENT_METHOD_STRIPE)
        source = Source(
            source_type=source_type,
            currency=settings.STRIPE_CURRENCY,
            amount_allocated=order_total.incl_tax,
            amount_debited=order_total.incl_tax,
            reference=pi)
        self.add_payment_source(source)

        self.add_payment_event(PAYMENT_EVENT_PURCHASE, order_total.incl_tax, reference=pi)

        del self.request.session["stripe_session_id"]
        del self.request.session["stripe_payment_intent_id"]

    def payment_description(self, order_number, total, **kwargs):
        return "Stripe payment for order {0} by {1}".format(order_number, self.request.user.get_full_name())
        
    def payment_metadata(self, order_number, total, **kwargs):
        return {
            'order_number': order_number,
        }


class ThankYouView(CoreThankYouView):
    template_name = "checkout/stripe_preview.html"


# @method_decorator(csrf_exempt, name='dispatch')
# class StripeWebhookView(PaymentDetailsView):
#     def post(self, request, **kwargs):
#         endpoint_secret = settings.STRIPE_ENDPOINT_SECRET
#         stripe.api_key = settings.STRIPE_SECRET_KEY
#         payload = request.body
#         sig_header = request.META['HTTP_STRIPE_SIGNATURE']
#         event = None
#
#         try:
#             event = stripe.Webhook.construct_event(
#                         payload, sig_header, endpoint_secret)
#         except ValueError as e:
#             # Invalid payload
#             return HttpResponse(status=400)
#         except stripe.error.SignatureVerificationError as e:
#             # Invalid signature
#             return HttpResponse(status=400)
#
#         # Handle the checkout.session.completed event
#         if event['type'] == 'checkout.session.completed':
#             session = event['data']['object']
#
#             # Fulfill the purchase...
#             self.handle_payment(
#                 session
#             )
#
#         return HttpResponse(status=204)