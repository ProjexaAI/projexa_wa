import json
import logging
import sys
import time
from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import Optional
import httpx

PROCESSED_WEBHOOKS: dict[str, float] = {}
WEBHOOK_TTL_SECONDS = 60

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
    force=True
)
logger = logging.getLogger("wa")

from config import OPENWA_API_URL, OPENWA_API_KEY, OPENWA_SESSION_ID
from agent.core import process_message
from agent.permissions import get_user_by_phone
from agent.document_upload import download_media_from_openwa, upload_to_r2

app = FastAPI(title="Projexa WhatsApp Agent")


class WebhookEvent(BaseModel):
    event: str
    session: Optional[str] = None
    data: Optional[dict] = None


def _is_duplicate_webhook(idempotency_key: str) -> bool:
    now = time.time()
    expired = [k for k, ts in PROCESSED_WEBHOOKS.items() if now - ts > WEBHOOK_TTL_SECONDS]
    for k in expired:
        del PROCESSED_WEBHOOKS[k]
    if idempotency_key in PROCESSED_WEBHOOKS:
        return True
    PROCESSED_WEBHOOKS[idempotency_key] = now
    return False


async def send_whatsapp_message(phone: str, text: str, chat_id: str | None = None):
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{OPENWA_API_URL}/sessions/{OPENWA_SESSION_ID}/messages/send-text"
        headers = {"Content-Type": "application/json", "X-API-Key": OPENWA_API_KEY}
        payload = {"chatId": chat_id or f"{phone}@c.us", "text": text}
        response = await client.post(url, json=payload, headers=headers)
        return response.json()


async def resolve_lid_to_phone(lid: str) -> str | None:
    async with httpx.AsyncClient() as client:
        url = f"{OPENWA_API_URL}/sessions/{OPENWA_SESSION_ID}/contacts/{lid}/phone"
        headers = {"Content-Type": "application/json", "X-API-Key": OPENWA_API_KEY}
        try:
            response = await client.get(url, headers=headers, timeout=5.0)
            if response.status_code == 200:
                return response.json().get("phone")
            return None
        except Exception:
            return None


async def send_whatsapp_document(phone: str, file_path: str, caption: str = "", chat_id: str | None = None):
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{OPENWA_API_URL}/sessions/{OPENWA_SESSION_ID}/messages/send-document"
        headers = {"Content-Type": "application/json", "X-API-Key": OPENWA_API_KEY}
        filename = file_path.split("/")[-1].split("?")[0] or "document.pdf"
        payload = {
            "chatId": chat_id or f"{phone}@c.us",
            "url": file_path,
            "filename": filename,
            "caption": caption
        }
        logger.info(f"send-document payload: {json.dumps(payload, indent=2)}")
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            logger.warning(f"send-document failed: {response.status_code} {response.text[:200]}")
        try:
            return response.json()
        except Exception:
            logger.error(f"send-document non-JSON response: {response.status_code} {response.text[:200]}")
            return {"error": f"Non-JSON response: {response.status_code}"}


async def send_whatsapp_image(phone: str, file_path: str, caption: str = "", chat_id: str | None = None):
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{OPENWA_API_URL}/sessions/{OPENWA_SESSION_ID}/messages/send-image"
        headers = {"Content-Type": "application/json", "X-API-Key": OPENWA_API_KEY}
        filename = file_path.split("/")[-1].split("?")[0] or "image.jpg"
        # Determine mimetype from extension
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpeg"
        mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}
        mimetype = mime_map.get(ext, f"image/{ext}")
        payload = {
            "chatId": chat_id or f"{phone}@c.us",
            "url": file_path,
            "mimetype": mimetype,
            "filename": filename,
            "caption": caption
        }
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code not in (200, 201):
            logger.warning(f"send-image failed: {response.status_code} {response.text[:200]}")
        return response.json()


async def send_whatsapp_video(phone: str, file_path: str, caption: str = "", chat_id: str | None = None):
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{OPENWA_API_URL}/sessions/{OPENWA_SESSION_ID}/messages/send-video"
        headers = {"Content-Type": "application/json", "X-API-Key": OPENWA_API_KEY}
        filename = file_path.split("/")[-1].split("?")[0] or "video.mp4"
        payload = {
            "chatId": chat_id or f"{phone}@c.us",
            "url": file_path,
            "filename": filename,
            "caption": caption
        }
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            logger.warning(f"send-video failed: {response.status_code} {response.text[:200]}")
        return response.json()


@app.post("/webhook")
async def handle_webhook(request: Request):
    body = await request.json()
    event = body.get("event")
    data = body.get("data", {})

    if event != "message.received":
        return {"status": "ignored"}

    idempotency_key = body.get("idempotencyKey")
    if idempotency_key and _is_duplicate_webhook(idempotency_key):
        return {"status": "duplicate"}

    message = data.get("body", data)
    raw_from = data.get("from", "") if isinstance(message, str) else message.get("from", data.get("from", ""))

    # Use data dict for metadata lookups (caption, fileName, id, type)
    # because message may be a string (just the text body)
    msg_data = message if isinstance(message, dict) else data

    if isinstance(message, str):
        text = message
        msg_type = data.get("type", "text")
    elif isinstance(message, dict):
        text_obj = message.get("text", {})
        text = text_obj.get("body", "") if isinstance(text_obj, dict) else str(text_obj)
        msg_type = message.get("type")
    else:
        return {"status": "invalid_message_format"}

    # Resolve phone number
    if raw_from.endswith("@lid"):
        phone = await resolve_lid_to_phone(raw_from) or raw_from.replace("@lid", "")
    else:
        phone = raw_from.replace("@c.us", "")

    # Handle different message types
    if msg_type == "image":
        caption = msg_data.get("caption", "") or ""
        text = f"[Image] {caption}".strip() or "[Image] Please describe what you need."
    elif msg_type == "audio":
        text = "[Audio] Please type your request."
    elif msg_type == "video":
        caption = msg_data.get("caption", "") or ""
        text = f"[Video] {caption}".strip() or "[Video] Please describe what you need."
    elif msg_type != "text":
        return {"status": "unsupported_message_type"}

    if not text.strip() and msg_type != "document":
        return {"status": "empty_message"}

    # Look up user
    user = get_user_by_phone(phone)
    if not user:
        await send_whatsapp_message(phone, "You are not registered in the system. Please contact admin.", chat_id=raw_from)
        return {"status": "user_not_found"}

    user_id = str(user["_id"])
    user_name = user.get("name", "User")
    user_role = (user.get("roles") or ["STUDENT"])[0]

    logger.info(f"Incoming: {phone} ({user_role}) | {text[:80]}")

    # For documents: upload to R2, then pass file info to AI
    if msg_type == "document":
        logger.info(f"Document detected. msg_data keys: {list(msg_data.keys()) if isinstance(msg_data, dict) else 'not dict'}")
        if isinstance(msg_data, dict):
            media = msg_data.get("media")
            logger.info(f"media field: {'present' if media else 'missing'}, type: {type(media).__name__ if media else 'N/A'}")
            if isinstance(media, dict):
                logger.info(f"media.keys: {list(media.keys())}, data_len: {len(media.get('data', ''))}")
        try:
            file_bytes, actual_filename, content_type = await download_media_from_openwa(
                msg_data.get("id") or msg_data.get("messageId") or "", msg_data
            )
            logger.info(f"Downloaded: {actual_filename} ({len(file_bytes)} bytes, {content_type})")
            upload_result = await upload_to_r2(file_bytes, actual_filename, content_type)

            # Build file info for AI
            caption = msg_data.get("caption", "") or ""
            file_info = (
                f"[User sent a document]\n"
                f"File: {actual_filename}\n"
                f"URL: {upload_result['fileUrl']}\n"
                f"ObjectKey: {upload_result['objectKey']}\n"
                f"Size: {upload_result['fileSizeBytes']} bytes\n"
                f"Type: {content_type}\n"
                f"Caption: {caption}"
            )
            text = file_info
            logger.info(f"Document uploaded to R2: {actual_filename} -> {upload_result['fileUrl']}")
            logger.info(f"Passing to AI: {file_info[:200]}")
        except Exception as e:
            logger.error(f"Document upload error: {phone} | {e}")
            await send_whatsapp_message(phone, f"Failed to process document: {str(e)}", chat_id=raw_from)
            return {"status": "upload_error", "detail": str(e)}

    try:
        result = await _process_async(user_id, user_name, user_role, text)

        response_text = result.get("text", "") if isinstance(result, dict) else str(result)
        media_items = result.get("media", []) if isinstance(result, dict) else []

        for media in media_items:
            media_url = media.get("url", "")
            media_type = media.get("type", "document")
            caption = media.get("caption", "")
            if media_type == "image":
                await send_whatsapp_image(phone, media_url, caption, chat_id=raw_from)
            elif media_type == "video":
                await send_whatsapp_video(phone, media_url, caption, chat_id=raw_from)
            elif media_type == "document":
                await send_whatsapp_document(phone, media_url, caption, chat_id=raw_from)
            logger.info(f"Sent {media_type} to {phone}")

        if response_text:
            await send_whatsapp_message(phone, response_text, chat_id=raw_from)
        return {"status": "sent"}
    except Exception as e:
        logger.error(f"Error: {phone} | {e}")
        await send_whatsapp_message(phone, "Sorry, something went wrong. Please try again.", chat_id=raw_from)
        return {"status": "error", "detail": str(e)}


async def _process_async(user_id: str, user_name: str, user_role: str, message: str) -> dict:
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: process_message(user_id, user_name, user_role, message))


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    from config import SERVER_HOST, SERVER_PORT
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
