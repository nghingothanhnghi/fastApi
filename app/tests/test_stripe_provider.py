from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.payments.providers.stripe_provider import (
    ZERO_DECIMAL_CURRENCIES,
    StripeProvider,
    normalize_currency,
    to_stripe_amount,
)


@pytest.mark.parametrize(
    "amount,currency,expected",
    [
        (310000, "vnd", 310000),      # the reported bug: was 31,000,000
        (310000.0, "VND", 310000),    # float + uppercase (billiard config sends "VND")
        (1000, "jpy", 1000),
        (50000, "krw", 50000),
        (19.99, "usd", 1999),         # int(19.99 * 100) == 1998 with floats
        (10, "USD", 1000),
        (0.01, "eur", 1),
        (1.234, "kwd", 1230),         # three-decimal, last digit must be 0
    ],
)
def test_to_stripe_amount(amount, currency, expected):
    assert to_stripe_amount(amount, currency) == expected


@pytest.mark.parametrize("amount", [0, -5, float("nan"), float("inf")])
def test_to_stripe_amount_rejects_invalid(amount):
    with pytest.raises(ValueError):
        to_stripe_amount(amount, "usd")


def test_normalize_currency():
    assert normalize_currency("VND") == "vnd"
    assert normalize_currency(" Usd ") == "usd"
    assert normalize_currency(None) == "usd"
    with pytest.raises(ValueError):
        normalize_currency("dollars")


def test_zero_decimal_set_contains_common_currencies():
    assert {"vnd", "jpy", "krw"} <= ZERO_DECIMAL_CURRENCIES


def test_create_payment_intent_vnd():
    fake = SimpleNamespace(id="pi_1", client_secret="sec", status="requires_payment_method")
    with patch("stripe.PaymentIntent.create", return_value=fake) as create:
        result = StripeProvider().create_payment_intent(310000.0, "VND", {"k": "v"})
    create.assert_called_once_with(amount=310000, currency="vnd", metadata={"k": "v"})
    assert result["id"] == "pi_1"


def test_create_payment_intent_usd():
    fake = SimpleNamespace(id="pi_2", client_secret="sec", status="requires_payment_method")
    with patch("stripe.PaymentIntent.create", return_value=fake) as create:
        StripeProvider().create_payment_intent(19.99, "USD")
    create.assert_called_once_with(amount=1999, currency="usd", metadata={})


def test_refund_partial_vnd_and_full():
    with patch("stripe.Refund.create") as refund:
        StripeProvider().refund_payment("pi_1", 100000, "vnd")
        refund.assert_called_with(payment_intent="pi_1", amount=100000)

        StripeProvider().refund_payment("pi_1")  # full refund: no amount sent
        refund.assert_called_with(payment_intent="pi_1")


def test_refund_partial_usd():
    with patch("stripe.Refund.create") as refund:
        StripeProvider().refund_payment("pi_2", 5.5, "usd")
    refund.assert_called_once_with(payment_intent="pi_2", amount=550)
