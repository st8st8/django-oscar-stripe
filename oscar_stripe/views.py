from django.conf import settings
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from oscar.core.loading import get_class, get_model

from oscar.apps.checkout.views import PaymentDetailsView as CorePaymentDetailsView
from oscar.apps.checkout.views import ThankYouView as CoreThankYouView

from apps.checkout import mixins
from oscar_stripe.facade import Facade

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
            ctx['stripe_token_form'] = forms.StripeTokenForm(self.request.POST)
            ctx['order_total_incl_tax_cents'] = (
                ctx['order_total'].incl_tax * 100
            ).to_integral_value()
        else:
            ctx['stripe_publishable_key'] = settings.STRIPE_PUBLISHABLE_KEY
        return ctx

    def handle_payment(self, order_number, total, **kwargs):
        stripe_ref = Facade().charge(
            order_number,
            total,
            card=self.request.POST[STRIPE_TOKEN],
            description=self.payment_description(order_number, total, **kwargs),
            metadata=self.payment_metadata(order_number, total, **kwargs),
            receipt_email=self.request.user.email if STRIPE_SEND_RECEIPT else None)

        source_type, __ = SourceType.objects.get_or_create(name=PAYMENT_METHOD_STRIPE)
        source = Source(
            source_type=source_type,
            currency=settings.STRIPE_CURRENCY,
            amount_allocated=total.incl_tax,
            amount_debited=total.incl_tax,
            reference=stripe_ref)
        self.add_payment_source(source)

        self.add_payment_event(PAYMENT_EVENT_PURCHASE, total.incl_tax)

    def payment_description(self, order_number, total, **kwargs):
        return "Stripe payment for order {0} by {1}".format(order_number, self.request.user.get_full_name())

    def load_basket(self):
        # Lookup the frozen basket that this txn corresponds to
        try:
            basket = self.get_submitted_basket()
        except Basket.DoesNotExist:
            return None

        # Assign strategy to basket instance
        if Selector:
            basket.strategy = Selector().strategy(self.request)
        print(basket.strategy)
        # Re-apply any offers
        Applicator().apply(basket, self.request.user, request=self.request)

        return basket
        
    def payment_metadata(self, order_number, total, **kwargs):
        return {
            'order_number': order_number,
        }
        
        basket = self.load_basket()
        items = [{
            "item": line.product.title,
            "quantity": line.quantity,
            "price": line.line_price_incl_tax,
        } for line in basket.all_lines()]


class ThankYouView(CoreThankYouView):
    template_name = "checkout/stripe_preview.html"
