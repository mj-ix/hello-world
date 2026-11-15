"""Optional real checkout through Stripe Payment Links (plain HTTPS, no SDK).

With STRIPE_SECRET_KEY set, every product the pet designs gets a hosted checkout
page. Without it the shop runs on an honour system: the buy button emails the pet.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ..config import Config

API = "https://api.stripe.com/v1"


class PaymentError(Exception):
    pass


class StripePayments:
    name = "stripe"

    def __init__(self, secret_key: str, opener=None):
        self._auth = "Basic " + base64.b64encode(f"{secret_key}:".encode()).decode()
        self._open = opener or urllib.request.urlopen

    def _post(self, path: str, form: dict[str, Any]) -> dict[str, Any]:
        data = urllib.parse.urlencode(form).encode()
        req = urllib.request.Request(f"{API}{path}", data=data, method="POST")
        req.add_header("Authorization", self._auth)
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with self._open(req, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise PaymentError(f"stripe {path} failed: {e.code} {e.read()[:200]!r}") from e
        except urllib.error.URLError as e:
            raise PaymentError(f"stripe unreachable: {e}") from e

    def create_payment_link(self, name: str, description: str, amount: float, currency: str, product_url: str = "") -> str:
        product = self._post("/products", {"name": name[:250], "description": description[:500] or name, "url": product_url} if product_url else {"name": name[:250], "description": description[:500] or name})
        price = self._post("/prices", {"product": product["id"], "unit_amount": int(round(amount * 100)), "currency": currency})
        link = self._post("/payment_links", {"line_items[0][price]": price["id"], "line_items[0][quantity]": 1})
        return link["url"]


def make_payments(config: Config) -> StripePayments | None:
    if config.stripe_secret_key:
        return StripePayments(config.stripe_secret_key)
    return None
