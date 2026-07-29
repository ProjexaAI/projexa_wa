import json
import hashlib
import hmac
import logging
import sys
import time
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from typing import Optional
import httpx

PROCESSED_WEBHOOKS: dict[str, float] = {}
WEBHOOK_TTL_SECONDS = 60

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
    force=True
)
logger = logging.getLogger("webhook")

from config import OPENWA_API_URL, OPENWA_API_KEY, OPENWA_SESSION_ID
from agent.core import process_message
from agent.permissions import get_user_by_phone

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
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": OPENWA_API_KEY
        }
        # Use provided chat_id, or build from phone
        if not chat_id:
            chat_id = f"{phone}@c.us"
        payload = {
            "chatId": chat_id,
            "text": text
        }
        logger.info(f"Sending message to {chat_id}: {text[:100]}...")
        response = await client.post(url, json=payload, headers=headers)
        logger.info(f"Send response status: {response.status_code}, body: {response.text[:200]}")
        return response.json()


async def resolve_lid_to_phone(lid: str) -> str | None:
    """Resolve a WhatsApp LID (e.g. 159558102180073@lid) to a phone number."""
    async with httpx.AsyncClient() as client:
        url = f"{OPENWA_API_URL}/sessions/{OPENWA_SESSION_ID}/contacts/{lid}/phone"
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": OPENWA_API_KEY
        }
        try:
            response = await client.get(url, headers=headers, timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                phone = data.get("phone")
                logger.info(f"LID resolution: {lid} -> {phone}")
                return phone
            else:
                logger.warning(f"LID resolution failed: {response.status_code} {response.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"LID resolution error: {e}")
            return None


async def send_whatsapp_document(phone: str, file_path: str, caption: str = ""):
    async with httpx.AsyncClient() as client:
        url = f"{OPENWA_API_URL}/sessions/{OPENWA_SESSION_ID}/messages/send-document"
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": OPENWA_API_KEY
        }
        payload = {
            "chatId": f"{phone}@c.us",
            "file": file_path,
            "caption": caption
        }
        response = await client.post(url, json=payload, headers=headers)
        return response.json()


@app.post("/webhook")
async def handle_webhook(request: Request):
    body = await request.json()
    logger.info(f"Webhook received: event={body.get('event')}, data_keys={list(body.get('data', {}).keys()) if isinstance(body.get('data'), dict) else type(body.get('data'))}")
    logger.debug(f"Full webhook body: {json.dumps(body, default=str)[:500]}")

    event = body.get("event")
    data = body.get("data", {})
    idempotency_key = body.get("idempotencyKey")

    # Only handle incoming messages
    if event != "message.received":
        logger.info(f"Ignoring event: {event}")
        return {"status": "ignored"}

    # Deduplicate webhook deliveries
    if idempotency_key:
        if _is_duplicate_webhook(idempotency_key):
            logger.info(f"Duplicate webhook ignored (idempotencyKey={idempotency_key})")
            return {"status": "duplicate"}
        logger.info(f"Processing new webhook (idempotencyKey={idempotency_key})")

    message = data.get("body", data)
    logger.debug(f"Message raw: {json.dumps(message, default=str)[:300] if isinstance(message, (dict, list)) else str(message)[:300]}")

    # Extract raw sender JID (may be @c.us or @lid)
    raw_from = data.get("from", "") if isinstance(message, str) else message.get("from", data.get("from", ""))

    if isinstance(message, str):
        text = message
        msg_type = data.get("type", "text")
    elif isinstance(message, dict):
        text_obj = message.get("text", {})
        text = text_obj.get("body", "") if isinstance(text_obj, dict) else str(text_obj)
        msg_type = message.get("type")
    else:
        logger.warning(f"Invalid message format: type={type(message)}")
        return {"status": "invalid_message_format"}

    # Resolve phone number from sender JID
    if raw_from.endswith("@lid"):
        logger.info(f"Sender is LID: {raw_from}, resolving to phone...")
        resolved_phone = await resolve_lid_to_phone(raw_from)
        if resolved_phone:
            phone = resolved_phone
            logger.info(f"LID resolved: {raw_from} -> {phone}")
        else:
            # Fallback: strip @lid and try lookup
            phone = raw_from.replace("@lid", "")
            logger.warning(f"LID resolution failed, using stripped value: {phone}")
    else:
        phone = raw_from.replace("@c.us", "")

    logger.info(f"Parsed: phone={phone}, msg_type={msg_type}, text={text[:100] if text else ''}")

    # Handle different message types
    if msg_type == "text":
        pass  # text already extracted
    elif msg_type == "image":
        text = "[Image received] " + (message.get("caption", "") or "Please describe what you need.")
    elif msg_type == "document":
        text = "[Document received] " + (message.get("caption", "") or "Please describe what you need.")
    elif msg_type == "audio":
        text = "[Audio message received] Please type your request."
    else:
        logger.warning(f"Unsupported message type: {msg_type}")
        return {"status": "unsupported_message_type"}

    if not text.strip():
        logger.info("Empty message, skipping")
        return {"status": "empty_message"}

    # Look up user by phone number
    logger.info(f"Looking up user by phone: {phone}")
    user = get_user_by_phone(phone)
    logger.info(f"User lookup result: {user}")
    if not user:
        logger.warning(f"User not found for phone: {phone}")
        await send_whatsapp_message(phone, "You are not registered in the system. Please contact admin.", chat_id=raw_from)
        return {"status": "user_not_found"}

    user_id = str(user["_id"])
    user_name = user.get("name", "User")
    user_roles = user.get("roles", ["STUDENT"])
    user_role = user_roles[0] if user_roles else "STUDENT"
    logger.info(f"User found: id={user_id}, name={user_name}, role={user_role}")

    try:
        logger.info(f"Processing message through AI agent...")
        response_text = await _process_async(user_id, user_name, user_role, text)
        logger.info(f"Agent response: {response_text[:200] if response_text else 'None'}")
        await send_whatsapp_message(phone, response_text, chat_id=raw_from)
        logger.info("Message sent successfully")
        return {"status": "sent"}
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        await send_whatsapp_message(phone, "Sorry, something went wrong. Please try again.", chat_id=raw_from)
        return {"status": "error", "detail": str(e)}


async def _process_async(user_id: str, user_name: str, user_role: str, message: str) -> str:
    import asyncio
    logger.info(f"_process_async called: user_id={user_id}, user_name={user_name}, user_role={user_role}, message={message[:100]}")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: process_message(user_id, user_name, user_role, message)
    )
    logger.info(f"_process_async result: {result[:200] if result else 'None'}")
    return result


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    from config import SERVER_HOST, SERVER_PORT
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
