"""Payment gateway abstraction. Default is a mock; plug Razorpay/Stripe in by subclassing."""
import secrets
from typing import Protocol


class PaymentGateway(Protocol):
    name: str

    def create_order(self, amount: float, currency: str, receipt: str) -> str: ...


class MockGateway:
    name = "mock"

    def create_order(self, amount: float, currency: str, receipt: str) -> str:
        return "order_" + secrets.token_hex(8)


def get_gateway() -> PaymentGateway:
    from .config import settings
    if settings.payment_provider == "mock":
        return MockGateway()
    raise NotImplementedError(f"Gateway '{settings.payment_provider}' not implemented")
