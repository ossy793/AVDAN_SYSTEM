"""
Vendor dashboard routes.
All routes require JWT with role=VENDOR.
"""
import uuid
from pathlib import Path
from typing import Annotated

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import VendorNotApproved
from app.core.rbac import CurrentUser, require_role
from app.database import get_db
from app.models.order import OrderStatus
from app.models.product import Product
from app.models.user import UserRole
from app.models.vendor import VendorProfile
from app.schemas.order import OrderOut, OrderRejectRequest, OrderSummary
from app.schemas.payment import PayoutRequest, PayoutResponse
from app.schemas.product import ProductCreate, ProductOut, ProductUpdate
from app.schemas.user import VendorProfileOut, VendorProfileUpdate
from app.schemas.wallet import WalletOut, WalletTransactionList, WalletTransactionOut
from app.services.order_service import OrderService
from app.services.payment_service import PaymentService
from app.services.wallet_service import WalletService
from app.utils.helpers import paginate_response

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_UPLOAD_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

router = APIRouter(dependencies=[Depends(require_role(UserRole.VENDOR))])


# ── Profile ───────────────────────────────────────────────────────────────────
@router.get("/profile", response_model=VendorProfileOut)
async def get_vendor_profile(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(VendorProfile).where(VendorProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Vendor profile not set up yet.")
    return VendorProfileOut.model_validate(profile)


@router.patch("/profile", response_model=VendorProfileOut)
async def update_vendor_profile(
    data: VendorProfileUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(VendorProfile).where(VendorProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Vendor profile not found.")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(profile, field, value)
    await db.commit()
    await db.refresh(profile)
    return VendorProfileOut.model_validate(profile)


# ── Products ──────────────────────────────────────────────────────────────────
@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    data: ProductCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    vendor_res = await db.execute(
        select(VendorProfile).where(VendorProfile.user_id == current_user.id)
    )
    vendor = vendor_res.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor profile not found.")
    if not vendor.is_approved:
        raise VendorNotApproved()

    product = Product(vendor_id=vendor.id, **data.model_dump())
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return ProductOut.model_validate(product)


@router.get("/products", summary="List my products")
async def list_my_products(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    vendor_res = await db.execute(
        select(VendorProfile).where(VendorProfile.user_id == current_user.id)
    )
    vendor = vendor_res.scalar_one_or_none()
    if not vendor:
        return paginate_response([], 0, page, per_page)

    count_res = await db.execute(
        select(func.count()).select_from(Product).where(Product.vendor_id == vendor.id)
    )
    total = count_res.scalar_one()
    result = await db.execute(
        select(Product)
        .where(Product.vendor_id == vendor.id)
        .order_by(Product.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    products = result.scalars().all()
    return paginate_response(
        [ProductOut.model_validate(p) for p in products], total, page, per_page
    )


@router.patch("/products/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: uuid.UUID,
    data: ProductUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    vendor_res = await db.execute(
        select(VendorProfile).where(VendorProfile.user_id == current_user.id)
    )
    vendor = vendor_res.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor profile not found.")

    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.vendor_id == vendor.id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(product, field, value)
    await db.commit()
    await db.refresh(product)
    return ProductOut.model_validate(product)


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    vendor_res = await db.execute(
        select(VendorProfile).where(VendorProfile.user_id == current_user.id)
    )
    vendor = vendor_res.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor profile not found.")

    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.vendor_id == vendor.id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    await db.delete(product)
    await db.commit()


# ── Orders ────────────────────────────────────────────────────────────────────
@router.get("/orders", summary="View incoming and active orders")
async def vendor_orders(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    order_status: OrderStatus | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
):
    vendor_res = await db.execute(
        select(VendorProfile).where(VendorProfile.user_id == current_user.id)
    )
    vendor = vendor_res.scalar_one_or_none()
    if not vendor:
        return paginate_response([], 0, page, per_page)

    svc = OrderService(db)
    orders, total = await svc.get_vendor_orders(vendor.id, order_status, page, per_page)
    return paginate_response(
        [OrderSummary.model_validate(o) for o in orders], total, page, per_page
    )


@router.get("/orders/{order_id}", response_model=OrderOut)
async def get_vendor_order(
    order_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    vendor_res = await db.execute(
        select(VendorProfile).where(VendorProfile.user_id == current_user.id)
    )
    vendor = vendor_res.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor profile not found.")
    svc = OrderService(db)
    order = await svc.get_order(order_id)
    if order.vendor_id != vendor.id:
        raise HTTPException(status_code=403, detail="Not your order.")
    return OrderOut.model_validate(order)


@router.post("/orders/{order_id}/confirm", response_model=OrderOut)
async def confirm_order(
    order_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Vendor accepts a paid order (PAID → VENDOR_CONFIRMED)."""
    svc = OrderService(db)
    order = await svc.get_order(order_id)
    vendor_res = await db.execute(
        select(VendorProfile).where(VendorProfile.user_id == current_user.id)
    )
    vendor = vendor_res.scalar_one_or_none()
    if not vendor or order.vendor_id != vendor.id:
        raise HTTPException(status_code=403, detail="Not your order.")
    order = await svc.transition(order_id, OrderStatus.VENDOR_CONFIRMED, current_user)
    return OrderOut.model_validate(order)


@router.post("/orders/{order_id}/reject", response_model=OrderOut)
async def reject_order(
    order_id: uuid.UUID,
    body: OrderRejectRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Vendor rejects a paid order (PAID → VENDOR_REJECTED). Triggers escrow refund."""
    vendor_res = await db.execute(
        select(VendorProfile).where(VendorProfile.user_id == current_user.id)
    )
    vendor = vendor_res.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor profile not found.")
    svc = OrderService(db)
    order = await svc.get_order(order_id)
    if order.vendor_id != vendor.id:
        raise HTTPException(status_code=403, detail="Not your order.")
    order = await svc.reject_order(order_id, current_user, body.reason)
    return OrderOut.model_validate(order)


@router.post("/orders/{order_id}/prepare", response_model=OrderOut)
async def mark_order_preparing(
    order_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Vendor starts preparing (VENDOR_CONFIRMED → PREPARING)."""
    svc = OrderService(db)
    order = await svc.transition(order_id, OrderStatus.PREPARING, current_user)
    return OrderOut.model_validate(order)


@router.post("/orders/{order_id}/ready", response_model=OrderOut)
async def mark_order_ready(
    order_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Vendor marks ready for pickup (PREPARING → READY_FOR_PICKUP)."""
    svc = OrderService(db)
    order = await svc.transition(order_id, OrderStatus.READY_FOR_PICKUP, current_user)
    return OrderOut.model_validate(order)


# ── Wallet & Payouts ──────────────────────────────────────────────────────────
@router.get("/wallet", response_model=WalletOut)
async def get_wallet(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    svc = WalletService(db)
    wallet = await svc.get_wallet(current_user.id)
    return WalletOut.model_validate(wallet)


@router.get("/wallet/transactions", response_model=WalletTransactionList)
async def wallet_transactions(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
):
    svc = WalletService(db)
    txs, total = await svc.get_transactions(current_user.id, page, per_page)
    return WalletTransactionList(
        transactions=[WalletTransactionOut.model_validate(t) for t in txs],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("/payout", response_model=PayoutResponse)
async def request_payout(
    data: PayoutRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    vendor_res = await db.execute(
        select(VendorProfile).where(VendorProfile.user_id == current_user.id)
    )
    vendor = vendor_res.scalar_one_or_none()
    if not vendor or not vendor.bank_account_number or not vendor.bank_code:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Bank account not set up. Please update your profile with bank details.",
        )
    svc = PaymentService(db)
    try:
        result = await svc.request_payout(
            user_id=current_user.id,
            amount=data.amount,
            account_number=vendor.bank_account_number,
            bank_code=vendor.bank_code,
            account_name=vendor.bank_name or vendor.business_name,
            reason=data.reason or "Vendor earnings withdrawal",
        )
    finally:
        await svc.aclose()
    return PayoutResponse(
        reference=result.get("reference", result.get("transactionReference", "")),
        amount=data.amount,
        status=result.get("status", "pending"),
        message="Payout initiated successfully.",
    )


# ── File uploads ──────────────────────────────────────────────────────────────
@router.post("/logo", summary="Upload vendor store logo")
async def upload_logo(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
):
    vendor_res = await db.execute(
        select(VendorProfile).where(VendorProfile.user_id == current_user.id)
    )
    vendor = vendor_res.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor profile not found.")

    if file.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only JPEG, PNG, and WebP images are allowed.",
        )

    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_MB} MB limit.",
        )

    upload_dir = Path(settings.UPLOAD_DIR) / "logos"
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "logo.jpg").suffix or ".jpg"
    dest = upload_dir / f"{vendor.id}{ext}"

    async with aiofiles.open(dest, "wb") as f:
        await f.write(content)

    vendor.logo_url = f"/uploads/logos/{vendor.id}{ext}"
    await db.commit()
    return {"logo_url": vendor.logo_url}


@router.post("/products/{product_id}/image", summary="Upload product image")
async def upload_product_image(
    product_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
):
    vendor_res = await db.execute(
        select(VendorProfile).where(VendorProfile.user_id == current_user.id)
    )
    vendor = vendor_res.scalar_one_or_none()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor profile not found.")

    product_res = await db.execute(
        select(Product).where(Product.id == product_id, Product.vendor_id == vendor.id)
    )
    product = product_res.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    if file.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only JPEG, PNG, and WebP images are allowed.",
        )

    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_MB} MB limit.",
        )

    upload_dir = Path(settings.UPLOAD_DIR) / "products"
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "image.jpg").suffix or ".jpg"
    dest = upload_dir / f"{product_id}{ext}"

    async with aiofiles.open(dest, "wb") as f:
        await f.write(content)

    product.image_url = f"/uploads/products/{product_id}{ext}"
    await db.commit()
    return {"image_url": product.image_url}
