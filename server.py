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

from config import OPENWA_API_URL, OPENWA_API_KEY, OPENWA_SESSION_ID, MASTER_ADMIN_PASSWORD
from agent.core import process_message
from agent.permissions import get_user_by_phone
from agent.document_upload import download_media_from_openwa, upload_to_r2
from agent.functions import get_user_by_email, list_users
from agent.db import get_collection

# Role priority: higher index = higher privilege
ROLE_PRIORITY = {"STUDENT": 0, "MENTOR": 1, "PLACEMENT_COORDINATOR": 2, "ADMIN": 3}

def _get_highest_role(roles: list[str] | None) -> str:
    """Return the highest-privilege role from a user's roles list."""
    if not roles:
        return "STUDENT"
    return max(roles, key=lambda r: ROLE_PRIORITY.get(r, 0))

app = FastAPI(title="Projexa WhatsApp Agent")

# Master admin state: {phone: {"state": "AWAITING_TARGET" | "IMPERSONATING", "target": user_dict}}
MASTER_ADMIN_STATES: dict[str, dict] = {}


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
    # text = text + "\n\n_🤖 This is an AI assistant. Information may not always be accurate. Please verify important details on the portal._"
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


def _lookup_user_by_identifier(identifier: str) -> dict | None:
    """Look up a user by email, roll number, or phone number."""
    identifier = identifier.strip()
    # Try email first
    user = get_user_by_email(identifier)
    if user:
        return user
    # Try roll number (exact or regex)
    user_data = get_collection("users").find_one(
        {"rollNumber": {"$regex": f"^{identifier}$", "$options": "i"}},
        {"_id": 1, "name": 1, "email": 1, "roles": 1, "mobileNumber": 1, "rollNumber": 1}
    )
    if user_data:
        return user_data
    # Try phone (reuse existing logic)
    user_data = get_user_by_phone(identifier)
    if user_data:
        return user_data
    # Try name search (fallback)
    results = list_users(search=identifier, page_size=1)
    if results.get("items"):
        return results["items"][0]
    return None


def _search_users(identifier: str) -> list[dict]:
    """Search users by name, email, roll number, or phone. Returns list of matching users."""
    identifier = identifier.strip()
    query = {
        "isActive": True,
        "$or": [
            {"isDeleted": False},
            {"isDeleted": {"$exists": False}},
            {"isDeleted": None}
        ]
    }
    search_regex = {"$regex": identifier, "$options": "i"}
    query["$or"] = [
        {"name": search_regex},
        {"email": search_regex},
        {"rollNumber": search_regex},
        {"mobileNumber": search_regex}
    ]
    results = list(get_collection("users").find(query).limit(10))
    return results


def _format_user_list(users: list[dict]) -> str:
    """Format a list of users for WhatsApp display."""
    lines = [f"Found {len(users)} user(s):\n"]
    for i, user in enumerate(users, 1):
        name = user.get("name", "Unknown")
        role = _get_highest_role(user.get("roles"))
        email = user.get("email", "N/A")
        roll = user.get("rollNumber", "N/A")
        phone = user.get("mobileNumber", "N/A")
        lines.append(f"*{i}. {name}* ({role})")
        lines.append(f"   Email: {email}")
        lines.append(f"   Roll: {roll}")
        lines.append(f"   Phone: {phone}\n")
    lines.append("Reply with the number (1, 2, etc.) to select.")
    return "\n".join(lines)


def _contains_master_password(text: str) -> bool:
    """Check if message contains the master admin password."""
    if not MASTER_ADMIN_PASSWORD:
        return False
    return MASTER_ADMIN_PASSWORD.lower() in text.lower()


async def _handle_master_admin(phone: str, text: str, chat_id: str) -> tuple[bool, str | None]:
    """
    Handle master admin flow. Returns (handled, response_text).
    If handled=True, the caller should send response_text and skip normal processing.
    """
    if not MASTER_ADMIN_PASSWORD:
        return False, None

    state = MASTER_ADMIN_STATES.get(phone)

    # Check if message contains the password (toggle or enter mode)
    if _contains_master_password(text):
        if state and state.get("state") == "IMPERSONATING":
            # Exit impersonation
            target_name = state["target"].get("name", "Unknown")
            del MASTER_ADMIN_STATES[phone]
            logger.info(f"[MASTER_ADMIN] {phone} exited impersonation of {target_name}")
            return True, f"Exited master admin mode. No longer acting as {target_name}."
        else:
            # Enter master admin mode (clear any existing state)
            MASTER_ADMIN_STATES[phone] = {"state": "AWAITING_TARGET"}
            logger.info(f"[MASTER_ADMIN] {phone} entered master admin mode")
            return True, (
                "Master admin mode activated.\n\n"
                "Send a name, email, roll number, or phone number to search for a user."
            )

    # If in AWAITING_TARGET state, search for users
    if state and state.get("state") == "AWAITING_TARGET":
        results = _search_users(text)
        if not results:
            return True, (
                "No users found matching that query.\n\n"
                "Try a different name, email, roll number, or phone number."
            )
        if len(results) == 1:
            # Single match — auto-select
            target_user = results[0]
            MASTER_ADMIN_STATES[phone] = {
                "state": "IMPERSONATING",
                "target": target_user
            }
            target_name = target_user.get("name", "Unknown")
            target_role = _get_highest_role(target_user.get("roles"))
            target_id = str(target_user["_id"])
            logger.info(f"[MASTER_ADMIN] {phone} now impersonating {target_name} ({target_role}, {target_id})")
            return True, (
                f"Now acting as *{target_name}* ({target_role}).\n"
                f"User ID: {target_id}\n\n"
                f"Send any message to interact as this user.\n"
                f"Send the master password again to exit."
            )
        else:
            # Multiple matches — show list
            MASTER_ADMIN_STATES[phone] = {
                "state": "AWAITING_SELECTION",
                "results": results
            }
            return True, _format_user_list(results)

    # If in AWAITING_SELECTION state, pick from results
    if state and state.get("state") == "AWAITING_SELECTION":
        try:
            choice = int(text.strip())
        except ValueError:
            return True, "Please reply with a number (e.g., 1, 2, 3)."
        results = state.get("results", [])
        if choice < 1 or choice > len(results):
            return True, f"Please pick a number between 1 and {len(results)}."
        target_user = results[choice - 1]
        MASTER_ADMIN_STATES[phone] = {
            "state": "IMPERSONATING",
            "target": target_user
        }
        target_name = target_user.get("name", "Unknown")
        target_role = _get_highest_role(target_user.get("roles"))
        target_id = str(target_user["_id"])
        logger.info(f"[MASTER_ADMIN] {phone} now impersonating {target_name} ({target_role}, {target_id})")
        return True, (
            f"Now acting as *{target_name}* ({target_role}).\n"
            f"User ID: {target_id}\n\n"
            f"Send any message to interact as this user.\n"
            f"Send the master password again to exit."
        )

    return False, None


@app.post("/webhook")
async def handle_webhook(request: Request):
    body = await request.json()
    event = body.get("event")
    data = body.get("data", {})

    # Debug: log all incoming webhooks
    logger.info(f"[WEBHOOK-IN] event={event} | data_keys={list(data.keys()) if isinstance(data, dict) else type(data).__name__}")
    if isinstance(data, dict):
        logger.info(f"[WEBHOOK-IN] from={data.get('from', 'N/A')} | type={data.get('type', 'N/A')} | body_preview={str(data.get('body', ''))[:200]}")

    # For groups: accept both message.received and message.sent
    is_group_msg = isinstance(data, dict) and data.get("from", "").endswith("@g.us")
    if event == "message.sent" and not is_group_msg:
        return {"status": "ignored"}
    if event not in ("message.received", "message.sent"):
        return {"status": "ignored"}

    idempotency_key = body.get("idempotencyKey")
    if idempotency_key and _is_duplicate_webhook(idempotency_key):
        logger.info(f"[WEBHOOK-IN] Duplicate webhook, skipping: {idempotency_key}")
        return {"status": "duplicate"}

    # Skip bot's own messages to avoid infinite loops
    if isinstance(data, dict) and data.get("fromMe"):
        return {"status": "ignored_self"}

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

    # Handle group messages (@g.us) — all group messages treated as master admin
    is_group = raw_from.endswith("@g.us")
    if is_group:
        # Debug: log full data dict to see available fields
        logger.info(f"[GROUP-DEBUG] raw_from={raw_from}")
        logger.info(f"[GROUP-DEBUG] data keys={list(data.keys())}")
        logger.info(f"[GROUP-DEBUG] data={json.dumps(data, default=str, indent=2)[:2000]}")
        # Extract sender's phone from author/sender field
        sender_phone = data.get("author", "") or data.get("sender", "") or data.get("participant", "")
        if sender_phone:
            phone = sender_phone.replace("@c.us", "").replace("@lid", "")
        else:
            logger.warning(f"[GROUP-DEBUG] No sender identified! data keys={list(data.keys())}")
            logger.warning(f"[GROUP-DEBUG] author={data.get('author')}, sender={data.get('sender')}, participant={data.get('participant')}")
            await send_whatsapp_message(phone, "I couldn't identify who sent this message.", chat_id=raw_from)
            return {"status": "group_sender_unknown"}
        chat_id = raw_from
        logger.info(f"[GROUP-ADMIN] {raw_from} | sender={phone} | {text[:80]}")
    else:
        chat_id = None  # Reply to individual

    # Resolve phone number
    if not is_group:
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
    elif msg_type not in ("text", "document"):
        return {"status": "unsupported_message_type"}

    if not text.strip() and msg_type != "document":
        return {"status": "empty_message"}

    # Group: handle "switch user" command
    if is_group and text.lower().startswith("switch user"):
        query = text[len("switch user"):].strip()
        if not query:
            await send_whatsapp_message(phone, "Usage: switch user <email, roll number, or name>", chat_id=chat_id)
            return {"status": "switch_usage"}
        results = _search_users(query)
        if not results:
            await send_whatsapp_message(phone, f"No users found matching: {query}", chat_id=chat_id)
            return {"status": "switch_no_match"}
        if len(results) == 1:
            target = results[0]
            MASTER_ADMIN_STATES[phone] = {"state": "IMPERSONATING", "target": target}
            name = target.get("name", "Unknown")
            role = _get_highest_role(target.get("roles"))
            uid = str(target["_id"])
            logger.info(f"[GROUP-ADMIN] {phone} switched to {name} ({role}, {uid})")
            await send_whatsapp_message(phone, f"Now acting as *{name}* ({role}).\nUser ID: {uid}", chat_id=chat_id)
            return {"status": "switched"}
        else:
            MASTER_ADMIN_STATES[phone] = {"state": "AWAITING_SELECTION", "results": results}
            await send_whatsapp_message(phone, _format_user_list(results), chat_id=chat_id)
            return {"status": "switch_select"}

    # Group: handle selection from switch user list
    if is_group and MASTER_ADMIN_STATES.get(phone, {}).get("state") == "AWAITING_SELECTION":
        try:
            choice = int(text.strip())
        except ValueError:
            await send_whatsapp_message(phone, "Please reply with a number (e.g., 1, 2, 3).", chat_id=chat_id)
            return {"status": "switch_invalid"}
        results = MASTER_ADMIN_STATES[phone].get("results", [])
        if choice < 1 or choice > len(results):
            await send_whatsapp_message(phone, f"Please pick a number between 1 and {len(results)}.", chat_id=chat_id)
            return {"status": "switch_invalid"}
        target = results[choice - 1]
        MASTER_ADMIN_STATES[phone] = {"state": "IMPERSONATING", "target": target}
        name = target.get("name", "Unknown")
        role = _get_highest_role(target.get("roles"))
        uid = str(target["_id"])
        logger.info(f"[GROUP-ADMIN] {phone} switched to {name} ({role}, {uid})")
        await send_whatsapp_message(phone, f"Now acting as *{name}* ({role}).\nUser ID: {uid}", chat_id=chat_id)
        return {"status": "switched"}

    # Master admin mode intercept
    master_handled, master_response = await _handle_master_admin(phone, text, chat_id)
    if master_handled:
        await send_whatsapp_message(phone, master_response, chat_id=chat_id)
        return {"status": "master_admin"}

    # Check if this phone is impersonating a user
    admin_state = MASTER_ADMIN_STATES.get(phone)
    if admin_state and admin_state.get("state") == "IMPERSONATING":
        target = admin_state["target"]
        user_id = str(target["_id"])
        user_name = target.get("name", "User")
        user_role = _get_highest_role(target.get("roles"))
        logger.info(f"Impersonating: {phone} -> {user_name} ({user_role}) | {text[:80]}")
    elif is_group:
        # Group: auto-impersonate sender if not already switched
        user = get_user_by_phone(phone)
        if not user:
            await send_whatsapp_message(phone, "You are not registered in the system.", chat_id=chat_id)
            return {"status": "user_not_found"}
        MASTER_ADMIN_STATES[phone] = {"state": "IMPERSONATING", "target": user}
        user_id = str(user["_id"])
        user_name = user.get("name", "User")
        user_role = _get_highest_role(user.get("roles"))
        logger.info(f"[GROUP-AUTO] {phone} auto-impersonating {user_name} ({user_role})")
    else:
        # Normal flow: look up user
        user = get_user_by_phone(phone)
        if not user:
            await send_whatsapp_message(phone, "You are not registered in the system. Please contact admin.", chat_id=chat_id)
            return {"status": "user_not_found"}
        user_id = str(user["_id"])
        user_name = user.get("name", "User")
        user_role = _get_highest_role(user.get("roles"))
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
            await send_whatsapp_message(phone, f"Failed to process document: {str(e)}", chat_id=chat_id)
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
                await send_whatsapp_image(phone, media_url, caption, chat_id=chat_id)
            elif media_type == "video":
                await send_whatsapp_video(phone, media_url, caption, chat_id=chat_id)
            elif media_type == "document":
                await send_whatsapp_document(phone, media_url, caption, chat_id=chat_id)
            logger.info(f"Sent {media_type} to {phone}")

        if response_text:
            await send_whatsapp_message(phone, response_text, chat_id=chat_id)
        return {"status": "sent"}
    except Exception as e:
        logger.error(f"Error: {phone} | {e}")
        await send_whatsapp_message(phone, "Sorry, something went wrong. Please try again.", chat_id=chat_id)
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
