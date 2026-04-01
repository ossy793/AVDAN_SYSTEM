"""
File upload endpoint.
POST /api/upload/image — accepts an image file, saves it to the uploads directory,
and returns the public URL.  Requires authentication.
"""
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.config import settings
from app.core.rbac import CurrentUser

router = APIRouter()

_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_EXT_MAP = {
    "image/jpeg": ".jpg",
    "image/png":  ".png",
    "image/webp": ".webp",
    "image/gif":  ".gif",
}
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


@router.post("/image", summary="Upload an image file")
async def upload_image(
    current_user: CurrentUser,
    file: UploadFile = File(...),
):
    """
    Accepts JPEG, PNG, WebP or GIF up to 5 MB.
    Returns { "url": "/uploads/products/<filename>" }
    """
    if file.content_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Allowed: JPEG, PNG, WebP, GIF.",
        )

    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum allowed size is 5 MB.",
        )

    ext = _EXT_MAP[file.content_type]
    filename = f"{uuid.uuid4().hex}{ext}"

    save_dir = Path(settings.UPLOAD_DIR) / "products"
    save_dir.mkdir(parents=True, exist_ok=True)
    (save_dir / filename).write_bytes(content)

    return {"url": f"/uploads/products/{filename}"}
