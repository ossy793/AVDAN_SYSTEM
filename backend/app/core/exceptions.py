"""
Centralised exception hierarchy.
All domain errors inherit from ADVANException so they can be caught uniformly.
"""
from fastapi import HTTPException, status


class ADVANException(HTTPException):
    """Base exception for all platform errors."""
    pass


# ── Auth ──────────────────────────────────────────────────────────────────────
class InvalidCredentials(ADVANException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )


class TokenExpired(ADVANException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
        )


# ── Resource ──────────────────────────────────────────────────────────────────
class NotFound(ADVANException):
    def __init__(self, resource: str = "Resource"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource} not found.",
        )


class AlreadyExists(ADVANException):
    def __init__(self, resource: str = "Resource"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{resource} already exists.",
        )


# ── Order ─────────────────────────────────────────────────────────────────────
class InvalidOrderTransition(ADVANException):
    def __init__(self, current: str, attempted: str):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Cannot transition order from '{current}' to '{attempted}'."
            ),
        )


class OrderNotAssignable(ADVANException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No available riders in this area.",
        )


# ── Payment ───────────────────────────────────────────────────────────────────
class PaymentFailed(ADVANException):
    def __init__(self, detail: str = "Payment processing failed."):
        super().__init__(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=detail,
        )


class InsufficientBalance(ADVANException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Insufficient wallet balance.",
        )


class EscrowReleaseError(ADVANException):
    def __init__(self, detail: str = "Failed to release escrow."):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
        )


# ── Vendor / Product ──────────────────────────────────────────────────────────
class ProductOutOfStock(ADVANException):
    def __init__(self, product_name: str = "Product"):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"'{product_name}' is out of stock.",
        )


class VendorNotApproved(ADVANException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor account is pending approval.",
        )


# ── Webhook ───────────────────────────────────────────────────────────────────
class WebhookVerificationFailed(ADVANException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook signature verification failed.",
        )
