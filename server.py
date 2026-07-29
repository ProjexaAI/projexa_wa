import json
import hashlib
import hmac
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from typing import Optional
import httpx

from config import OPENWA_API_URL, OPENWA_API_KEY, OPENWA_SESSION_ID
from agent.core import process_message
from agent.permissions import get_user_by_phone

app = FastAPI(title="Projexa WhatsApp Agent")


class WebhookEvent(BaseModel):
    event: str
    session: Optional[str] = None
    data: Optional[dict] = None


async def send_whatsapp_message(phone: str, text: str):
    async with httpx.AsyncClient() as client:
        url = f"{OPENWA_API_URL}/sessions/{OPENWA_SESSION_ID}/messages/send-text"
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": OPENWA_API_KEY
        }
        payload = {
            "chatId": f"{phone}@c.us",
            "text": text
        }
        response = await client.post(url, json=payload, headers=headers)
        return response.json()


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

    event = body.get("event")
    data = body.get("data", {})

    # Only handle incoming messages
    if event != "message.received":
        return {"status": "ignored"}

    message = data.get("body", {})
    text = message.get("text", {}).get("body", "")
    phone = message.get("from", "").replace("@c.us", "")
    msg_type = message.get("type")

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
        return {"status": "unsupported_message_type"}

    if not text.strip():
        return {"status": "empty_message"}

    # Look up user by phone number
    user = get_user_by_phone(phone)
    if not user:
        await send_whatsapp_message(phone, "You are not registered in the system. Please contact admin.")
        return {"status": "user_not_found"}

    user_id = str(user["_id"])
    user_name = user.get("name", "User")
    user_roles = user.get("roles", ["STUDENT"])
    user_role = user_roles[0] if user_roles else "STUDENT"

    try:
        # Process message through AI agent
        response_text = await _process_async(user_id, user_name, user_role, text)
        await send_whatsapp_message(phone, response_text)
        return {"status": "sent"}
    except Exception as e:
        await send_whatsapp_message(phone, "Sorry, something went wrong. Please try again.")
        return {"status": "error", "detail": str(e)}


async def _process_async(user_id: str, user_name: str, user_role: str, message: str) -> str:
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: process_message(user_id, user_name, user_role, message)
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    from config import SERVER_HOST, SERVER_PORT
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
