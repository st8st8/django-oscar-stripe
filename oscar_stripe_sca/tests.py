import json
import os
from os.path import dirname
from django.test import TestCase


# Create your tests here.
from django.urls import reverse


class StripeSCATestCase(TestCase):
    def test_webhook_checkout_success(self):
        filename = os.path.join(
            dirname(__file__),
            "fixtures/test-webhook.json"
        )
        webhook = None
        with open(filename, "r") as f:
            webhook = f.read()

        response = self.client.post(
            reverse("oscar_stripe_sca:webhook"),
            content_type="application/json",
            data=webhook
        )
        print(response)