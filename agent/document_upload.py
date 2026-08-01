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
from bson import ObjectId

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


async def download_media_from_openwa(message_id: str, webhook_data: dict = None) -> tuple[bytes, str, str]:
    """Extract media from OpenWA webhook payload.

    OpenWA returns media inline in webhook under the "media" field:
    { media: { mimetype, filename, data } }
    """
    if not webhook_data:
        raise ValueError("No webhook data provided — cannot extract media")

    # OpenWA puts media in a nested "media" object
    media = webhook_data.get("media")
    if isinstance(media, dict):
        raw_b64 = media.get("data", "")
        filename = media.get("filename") or media.get("fileName") or "document"
        content_type = media.get("mimetype") or media.get("mimeType") or "application/octet-stream"

        if raw_b64 and isinstance(raw_b64, str):
            try:
                file_bytes = base64.b64decode(raw_b64)
                if len(file_bytes) > 10:
                    logger.info(f"Extracted media: {filename} ({len(file_bytes)} bytes, {content_type})")
                    return file_bytes, filename, content_type
            except Exception as e:
                raise ValueError(f"Failed to decode base64 media: {e}")

    # Fallback: try top-level fields
    filename = (
        webhook_data.get("fileName")
        or webhook_data.get("filename")
        or webhook_data.get("caption")
        or "document"
    )
    content_type = (
        webhook_data.get("mimetype")
        or webhook_data.get("mimeType")
        or webhook_data.get("contentType")
        or "application/octet-stream"
    )

    for field in ("data", "buffer", "base64", "body", "content"):
        raw = webhook_data.get(field)
        if raw and isinstance(raw, str) and len(raw) > 100:
            try:
                file_bytes = base64.b64decode(raw)
                if len(file_bytes) > 10:
                    logger.info(f"Extracted media from '{field}': {filename} ({len(file_bytes)} bytes)")
                    return file_bytes, filename, content_type
            except Exception:
                continue

    raise ValueError(f"Could not extract media. media field: {media}")


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
    caption = message_data.get("caption", "")

    if not message_id:
        return {"success": False, "message": "Could not identify the message to download.", "file_url": None}

    try:
        # 1. Download from OpenWA (pass webhook data for inline media)
        file_bytes, actual_filename, content_type = await download_media_from_openwa(message_id, message_data)

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
        # List unsubmitted templates so user can pick
        from agent.db import get_collection
        enrollment_id, templates = _get_track_templates(user)
        submissions = list(get_collection("trackonboardingsubmissions").find({
            "enrollmentId": ObjectId(enrollment_id),
        }))
        submitted_ids = set()
        for sub in submissions:
            tpl_id = sub.get("documentTemplateId")
            if tpl_id and sub.get("status") in ("APPROVED", "SUBMITTED", "PENDING", "RESUBMITTED"):
                submitted_ids.add(str(tpl_id))

        unsubmitted = [t for t in templates if str(t.get("_id")) not in submitted_ids]

        if len(unsubmitted) == 0:
            return {
                "success": True,
                "message": f"Document '{actual_filename}' uploaded successfully.\nURL: {upload_result['fileUrl']}\n\nAll required documents are already submitted.",
                "file_url": upload_result["fileUrl"],
            }

        tpl_list = "\n".join(f"- {t.get('title', 'Untitled')}" for t in unsubmitted)
        return {
            "success": True,
            "message": (
                f"Document '{actual_filename}' uploaded successfully.\n"
                f"URL: {upload_result['fileUrl']}\n\n"
                f"Which document is this? Reply with the number:\n{tpl_list}"
            ),
            "file_url": upload_result["fileUrl"],
            "unsubmitted_templates": [{"id": str(t["_id"]), "title": t.get("title")} for t in unsubmitted],
        }

    except Exception as e:
        logger.exception("Document upload failed")
        return {"success": False, "message": f"Upload failed: {str(e)}", "file_url": None}


def _get_track_templates(user: dict) -> tuple[str, list[dict]]:
    """Get document templates for user's enrollment.

    Returns (enrollment_id_str, templates_list).
    Handles the case where enrollment's track config has 0 templates
    by falling back to the track config that owns the submitted templates.
    """
    from agent.db import get_collection

    session = get_collection("academicyears").find_one({"isActive": True})
    if not session:
        return None, []

    enrollment = get_collection("studenttrackenrollments").find_one({
        "studentId": user["_id"],
        "sessionId": session["_id"],
        "status": "ACTIVE",
    })
    if not enrollment:
        return None, []

    enrollment_id = str(enrollment["_id"])
    tc_id = enrollment.get("trackSessionConfigId")

    # Try enrollment's track config first
    if tc_id:
        tc = get_collection("tracksessionconfigs").find_one({"_id": tc_id})
        if tc:
            templates = [t for t in (tc.get("documentTemplates") or []) if t.get("isActive", True)]
            if templates:
                return enrollment_id, templates

    # Fallback: find track config via existing submissions
    submissions = list(get_collection("trackonboardingsubmissions").find({
        "enrollmentId": enrollment["_id"],
    }))
    submitted_tpl_ids = set()
    for sub in submissions:
        tpl_id = sub.get("documentTemplateId")
        if tpl_id:
            submitted_tpl_ids.add(str(tpl_id))

    all_tcs = get_collection("tracksessionconfigs").find({"sessionId": session["_id"]})
    for tc in all_tcs:
        for tmpl in (tc.get("documentTemplates") or []):
            if str(tmpl.get("_id")) in submitted_tpl_ids:
                # Found the right track config — return ALL its templates
                return enrollment_id, [t for t in (tc.get("documentTemplates") or []) if t.get("isActive", True)]

    return enrollment_id, []


def _extract_template_id(caption: str, user: dict) -> str | None:
    """Try to map caption text to a document template ID.

    1. Match by caption text against template names/codes
    2. If no caption match and only one unsubmitted template exists, auto-select it
    """
    from agent.db import get_collection

    enrollment_id, templates = _get_track_templates(user)
    if not templates:
        return None

    # Get existing submissions
    submissions = list(get_collection("trackonboardingsubmissions").find({
        "enrollmentId": ObjectId(enrollment_id),
    }))
    submitted_ids = set()
    for sub in submissions:
        tpl_id = sub.get("documentTemplateId")
        if tpl_id and sub.get("status") in ("APPROVED", "SUBMITTED", "PENDING", "RESUBMITTED"):
            submitted_ids.add(str(tpl_id))

    # 1. Try caption match
    if caption:
        caption_lower = caption.lower().strip()
        for tpl in templates:
            name = (tpl.get("title", "") or "").lower()
            code = (tpl.get("code", "") or "").lower()
            if name and name in caption_lower:
                return str(tpl["_id"])
            if code and code in caption_lower:
                return str(tpl["_id"])

    return None


async def get_pending_uploads(user_id: str) -> list[dict]:
    """List recent R2 uploads that haven't been submitted yet.

    Could be extended to track pending uploads in a collection.
    """
    return []
