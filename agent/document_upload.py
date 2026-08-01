"""Document upload handler for WhatsApp.

Downloads media from OpenWA, uploads to R2, submits via web app API.
"""

import base64
import logging
import mimetypes
import uuid
from datetime import datetime, timezone, timedelta

import boto3
import httpx
import jwt

from config import (
    JWT_SECRET, WEBAPP_BASE_URL,
    OPENWA_API_URL, OPENWA_API_KEY, OPENWA_SESSION_ID,
    R2_ACCESS_KEY, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME,
    R2_ENDPOINT_URL, R2_CDN_BASE_URL,
)

logger = logging.getLogger("wa.upload")

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
    "text/plain",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "application/zip",
}

MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB


def _r2_client():
    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT_URL,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


def _build_object_key(filename: str, folder: str = "uploads") -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    safe_name = "".join(c if c.isalnum() or c in "._-" else "-" for c in filename.rsplit(".", 1)[0])
    safe_name = safe_name[:60] or "file"
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return f"{folder}/{uuid.uuid4().hex[:12]}/{ts}-{safe_name}.{ext}"


def _guess_content_type(filename: str) -> str:
    mt, _ = mimetypes.guess_type(filename)
    if mt and mt in ALLOWED_CONTENT_TYPES:
        return mt
    if mt and mt == "image/jpg":
        return "image/jpeg"
    return "application/octet-stream"


async def download_media_from_openwa(message_id: str) -> tuple[bytes, str, str]:
    """Download media from OpenWA gateway.

    Returns (file_bytes, filename, content_type).
    """
    url = f"{OPENWA_API_URL}/sessions/{OPENWA_SESSION_ID}/media/{message_id}"
    headers = {"X-API-Key": OPENWA_API_KEY}

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()

    content_type = resp.headers.get("content-type", "")
    content_disp = resp.headers.get("content-disposition", "")

    # Extract filename from Content-Disposition if present
    filename = "document"
    if "filename=" in content_disp:
        filename = content_disp.split("filename=")[-1].strip('" ').split(";")[0]

    # If JSON response (some OpenWA versions return base64)
    if "json" in content_type:
        data = resp.json()
        if isinstance(data, dict):
            # Try common fields
            raw = data.get("data") or data.get("buffer") or data.get("base64") or ""
            file_bytes = base64.b64decode(raw) if raw else b""
            filename = data.get("filename") or data.get("fileName") or filename
            content_type = data.get("mimetype") or data.get("mimeType") or content_type
        else:
            file_bytes = resp.content
    else:
        file_bytes = resp.content

    if not file_bytes:
        raise ValueError("Downloaded file is empty")

    if len(file_bytes) > MAX_FILE_SIZE:
        raise ValueError(f"File too large: {len(file_bytes)} bytes (max {MAX_FILE_SIZE})")

    # Normalize content type
    ct = content_type.split(";")[0].strip().lower()
    if ct == "image/jpg":
        ct = "image/jpeg"
    if not ct or ct == "application/octet-stream":
        ct = _guess_content_type(filename)

    logger.info(f"Downloaded from OpenWA: {filename} ({len(file_bytes)} bytes, {ct})")
    return file_bytes, filename, ct


def generate_user_jwt(user: dict) -> str:
    """Generate a JWT that the web app will accept."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["_id"]),
        "email": user.get("email", ""),
        "roles": user.get("roles", ["STUDENT"]),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


async def upload_to_r2(file_bytes: bytes, filename: str, content_type: str) -> dict:
    """Upload file directly to R2. Returns metadata dict."""
    object_key = _build_object_key(filename)

    s3 = _r2_client()
    s3.put_object(
        Bucket=R2_BUCKET_NAME,
        Key=object_key,
        Body=file_bytes,
        ContentType=content_type,
    )

    file_url = f"{R2_CDN_BASE_URL}/{object_key}"
    logger.info(f"Uploaded to R2: {object_key} -> {file_url}")

    return {
        "objectKey": object_key,
        "fileUrl": file_url,
        "fileName": filename,
        "fileSizeBytes": len(file_bytes),
        "contentType": content_type,
    }


async def submit_via_webapp(jwt_token: str, document_template_id: str, files: list[dict]) -> dict:
    """Submit document to the web app's API."""
    url = f"{WEBAPP_BASE_URL}/api/student/tracks/onboarding/documents"
    headers = {
        "Content-Type": "application/json",
        "Cookie": f"internship_token={jwt_token}",
    }
    payload = {
        "documentTemplateId": document_template_id,
        "files": files,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        data = resp.json()
        logger.info(f"Webapp submission: {resp.status_code} {data}")
        return {"status_code": resp.status_code, **data}


async def handle_document_upload(user: dict, message_data: dict) -> dict:
    """Main entry: download, upload to R2, submit.

    Returns {"success": bool, "message": str, "file_url": str|None}
    """
    message_id = message_data.get("id") or message_data.get("messageId") or ""
    filename = (
        message_data.get("fileName")
        or message_data.get("filename")
        or message_data.get("caption")
        or "document"
    )
    caption = message_data.get("caption", "")

    if not message_id:
        return {"success": False, "message": "Could not identify the message to download.", "file_url": None}

    try:
        # 1. Download from OpenWA
        file_bytes, actual_filename, content_type = await download_media_from_openwa(message_id)

        # 2. Validate content type
        if content_type not in ALLOWED_CONTENT_TYPES:
            return {
                "success": False,
                "message": f"File type '{content_type}' is not allowed. Supported: PDF, DOC, DOCX, XLS, XLSX, CSV, TXT, JPG, PNG, WEBP, ZIP.",
                "file_url": None,
            }

        # 3. Upload to R2
        upload_result = await upload_to_r2(file_bytes, actual_filename, content_type)

        # 4. Generate JWT
        token = generate_user_jwt(user)

        # 5. Try to extract document template ID from caption
        template_id = _extract_template_id(caption, user)

        if template_id:
            # 6. Submit via webapp
            files = [{
                "fileName": upload_result["fileName"],
                "fileUrl": upload_result["fileUrl"],
                "objectKey": upload_result["objectKey"],
                "fileSizeBytes": upload_result["fileSizeBytes"],
                "contentType": upload_result["contentType"],
            }]
            result = await submit_via_webapp(token, template_id, files)

            if result.get("status_code") in (200, 201):
                return {
                    "success": True,
                    "message": f"Document '{actual_filename}' uploaded and submitted successfully.",
                    "file_url": upload_result["fileUrl"],
                }
            else:
                msg = result.get("message", "Unknown error")
                return {
                    "success": False,
                    "message": f"File uploaded but submission failed: {msg}",
                    "file_url": upload_result["fileUrl"],
                }

        # No template ID — file is on R2 but not submitted yet
        return {
            "success": True,
            "message": (
                f"Document '{actual_filename}' uploaded successfully.\n"
                f"URL: {upload_result['fileUrl']}\n\n"
                f"To complete submission, please tell me which document type this is "
                f"(e.g., 'submit as passport', 'upload transcript')."
            ),
            "file_url": upload_result["fileUrl"],
        }

    except Exception as e:
        logger.exception("Document upload failed")
        return {"success": False, "message": f"Upload failed: {str(e)}", "file_url": None}


def _extract_template_id(caption: str, user: dict) -> str | None:
    """Try to map caption text to a document template ID.

    Looks up active onboarding templates and matches by name/keyword.
    """
    if not caption:
        return None

    from agent.db import get_collection

    caption_lower = caption.lower().strip()

    # Find active session
    session = get_collection("academicyears").find_one({"isActive": True})
    if not session:
        return None

    # Find student's active enrollment
    enrollment = get_collection("studenttrackenrollments").find_one({
        "studentId": user["_id"],
        "sessionId": session["_id"],
        "status": "ACTIVE",
    })
    if not enrollment:
        return None

    # Find onboarding templates for this track
    templates = list(get_collection("trackonboardingtemplates").find({
        "trackId": enrollment.get("trackId"),
        "isActive": True,
    }))

    # Match by name keywords
    for tpl in templates:
        name = (tpl.get("name", "") or "").lower()
        keywords = (tpl.get("keywords", []) or [])
        doc_type = (tpl.get("documentType", "") or "").lower()

        if any(kw.lower() in caption_lower for kw in keywords):
            return str(tpl["_id"])
        if name and name in caption_lower:
            return str(tpl["_id"])
        if doc_type and doc_type in caption_lower:
            return str(tpl["_id"])

    return None


async def get_pending_uploads(user_id: str) -> list[dict]:
    """List recent R2 uploads that haven't been submitted yet.

    Could be extended to track pending uploads in a collection.
    """
    return []
