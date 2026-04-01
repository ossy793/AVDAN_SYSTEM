"""
Payment routes.
- Monnify webhook (public, HMAC-SHA512 verified)
- Manual payment verification (for redirect-back flow)
- Demo confirmation page (investor demo only — guarded by DEMO_MODE)
"""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.services.payment_service import PaymentService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/webhook/monnify",
    status_code=status.HTTP_200_OK,
    summary="Monnify webhook endpoint — do not call manually",
    include_in_schema=False,   # hide from docs to reduce attack surface
)
async def monnify_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Monnify sends POST here on every transaction/disbursement event.
    We verify HMAC-SHA512 before processing.
    """
    raw_body = await request.body()
    signature = request.headers.get("monnify-signature", "")

    svc = PaymentService(db)
    try:
        await svc.handle_webhook(raw_body, signature)
    except Exception as e:
        logger.error("Webhook processing error: %s", e)
        # Always return 200 to Monnify so it does not retry indefinitely.
    finally:
        await svc.aclose()

    return {"status": "ok"}


@router.get(
    "/verify",
    summary="Manually verify a payment after Monnify redirect",
)
async def verify_payment(
    reference: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    svc = PaymentService(db)
    try:
        payment = await svc.verify_and_confirm(reference)
        return {
            "status": payment.status.value,
            "order_id": str(payment.order_id),
            "amount": float(payment.amount),
            "reference": payment.reference,
        }
    finally:
        await svc.aclose()


@router.get(
    "/demo/confirmed",
    response_class=HTMLResponse,
    include_in_schema=False,
    summary="Demo payment confirmation page (DEMO_MODE only)",
)
async def demo_confirmed(reference: str = Query(default="")):
    """
    Investor-facing confirmation page shown after a demo payment.
    Only available when DEMO_MODE=true.
    """
    if not settings.DEMO_MODE:
        return HTMLResponse("<h3>Not found</h3>", status_code=404)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>ADVAN — Payment Confirmed</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f0fdf4;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 24px;
    }}
    .card {{
      background: #fff;
      border-radius: 16px;
      box-shadow: 0 4px 32px rgba(0,0,0,.10);
      max-width: 560px;
      width: 100%;
      padding: 40px 36px 36px;
      text-align: center;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: #dcfce7;
      color: #166534;
      font-size: 12px;
      font-weight: 600;
      padding: 4px 12px;
      border-radius: 999px;
      margin-bottom: 20px;
      letter-spacing: .5px;
      text-transform: uppercase;
    }}
    .checkmark {{
      width: 72px;
      height: 72px;
      background: #16a34a;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 20px;
    }}
    .checkmark svg {{ width: 36px; height: 36px; }}
    h1 {{ font-size: 24px; color: #111827; margin-bottom: 8px; }}
    .sub {{ color: #6b7280; font-size: 14px; margin-bottom: 32px; }}
    .ref {{
      background: #f9fafb;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      padding: 10px 16px;
      font-size: 13px;
      color: #6b7280;
      margin-bottom: 32px;
    }}
    .ref span {{ font-weight: 600; color: #374151; }}

    /* Escrow flow steps */
    .steps {{ text-align: left; margin-bottom: 32px; }}
    .steps h2 {{
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: .5px;
      color: #9ca3af;
      margin-bottom: 16px;
    }}
    .step {{
      display: flex;
      align-items: flex-start;
      gap: 14px;
      padding: 14px 0;
      border-bottom: 1px solid #f3f4f6;
    }}
    .step:last-child {{ border-bottom: none; }}
    .step-icon {{
      width: 36px;
      height: 36px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 16px;
      flex-shrink: 0;
    }}
    .step-icon.done  {{ background: #dcfce7; }}
    .step-icon.hold  {{ background: #fef9c3; }}
    .step-icon.pend  {{ background: #f3f4f6; }}
    .step-body h3 {{ font-size: 14px; font-weight: 600; color: #111827; margin-bottom: 2px; }}
    .step-body p  {{ font-size: 13px; color: #6b7280; line-height: 1.5; }}

    .btn {{
      display: inline-block;
      background: #16a34a;
      color: #fff;
      text-decoration: none;
      padding: 12px 32px;
      border-radius: 8px;
      font-size: 15px;
      font-weight: 600;
      transition: background .2s;
    }}
    .btn:hover {{ background: #15803d; }}
    .demo-note {{
      margin-top: 24px;
      font-size: 12px;
      color: #9ca3af;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="badge">&#x2022; Demo Mode Active</div>

    <div class="checkmark">
      <svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3"
           stroke-linecap="round" stroke-linejoin="round">
        <polyline points="20 6 9 17 4 12"/>
      </svg>
    </div>

    <h1>Payment Confirmed!</h1>
    <p class="sub">Funds are now held securely in escrow until delivery.</p>

    <div class="ref">
      Reference: <span>{reference or "DEMO-REF-001"}</span>
    </div>

    <div class="steps">
      <h2>How ADVAN Escrow Works</h2>

      <div class="step">
        <div class="step-icon done">💳</div>
        <div class="step-body">
          <h3>1. Payment Received &amp; Locked</h3>
          <p>Customer pays. Funds are locked in escrow — the vendor cannot touch them yet.</p>
        </div>
      </div>

      <div class="step">
        <div class="step-icon done">🏪</div>
        <div class="step-body">
          <h3>2. Vendor Notified &amp; Confirms</h3>
          <p>Vendor receives the order, confirms stock availability, and begins preparing the package.</p>
        </div>
      </div>

      <div class="step">
        <div class="step-icon hold">🛵</div>
        <div class="step-body">
          <h3>3. Rider Assigned &amp; Picks Up</h3>
          <p>Nearest available rider is assigned. Real-time GPS tracking begins for the customer.</p>
        </div>
      </div>

      <div class="step">
        <div class="step-icon hold">📦</div>
        <div class="step-body">
          <h3>4. Agent Hub Verification</h3>
          <p>Package passes through a verification hub. Agent scans and confirms contents before final delivery.</p>
        </div>
      </div>

      <div class="step">
        <div class="step-icon pend">✅</div>
        <div class="step-body">
          <h3>5. Delivered → Escrow Released</h3>
          <p>On confirmed delivery, escrow splits automatically: vendor earnings + rider commission credited to their wallets instantly.</p>
        </div>
      </div>
    </div>

    <button class="btn" onclick="window.close(); setTimeout(()=>{{if(!window.closed)window.history.back()}},300)">← Back to Customer App</button>

    <p class="demo-note">
      This is a simulated payment for investor demonstration purposes.<br>
      No real money was charged. Monnify live keys activate this in production.
    </p>
  </div>
</body>
</html>"""

    return HTMLResponse(content=html, status_code=200)
