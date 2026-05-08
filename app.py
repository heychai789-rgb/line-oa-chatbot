"""
Line OA Chatbot - "ลินดา"
AI Chatbot สำหรับ Line Official Account
ใช้ FastAPI + Line Messaging API + OpenAI GPT
"""

import os
import asyncio
import hashlib
import hmac
import base64
import json
import logging
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from openai import OpenAI
from chat_state import ChatStateManager

# ตั้งค่า logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment Variables
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# LINE API endpoints
LINE_API_BASE = "https://api.line.me/v2/bot"
LINE_REPLY_URL = f"{LINE_API_BASE}/message/reply"
LINE_PUSH_URL = f"{LINE_API_BASE}/message/push"

# OpenAI client
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Chat state manager
state_manager = ChatStateManager()

# Per-user asyncio locks เพื่อป้องกัน race condition (bot ตอบซ้ำ)
_user_locks: dict[str, asyncio.Lock] = {}


def get_user_lock(user_id: str) -> asyncio.Lock:
    """ดึง asyncio.Lock สำหรับ user แต่ละคน (สร้างใหม่ถ้ายังไม่มี)."""
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()
    return _user_locks[user_id]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info("🚀 Line OA Chatbot 'ลินดา' started!")
    logger.info(f"LINE_CHANNEL_SECRET configured: {'Yes' if LINE_CHANNEL_SECRET else 'No'}")
    logger.info(f"LINE_CHANNEL_ACCESS_TOKEN configured: {'Yes' if LINE_CHANNEL_ACCESS_TOKEN else 'No'}")
    logger.info(f"OPENAI_API_KEY configured: {'Yes' if OPENAI_API_KEY else 'No'}")
    yield
    logger.info("👋 Line OA Chatbot shutting down...")


app = FastAPI(
    title="Line OA Chatbot - ลินดา",
    description="AI Chatbot สำหรับ Line Official Account",
    version="1.0.0",
    lifespan=lifespan,
)


# =============================================================================
# Utility Functions
# =============================================================================


def verify_signature(body: bytes, signature: str) -> bool:
    """ตรวจสอบ signature จาก LINE Platform."""
    hash_value = hmac.new(
        LINE_CHANNEL_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    expected_signature = base64.b64encode(hash_value).decode("utf-8")
    return hmac.compare_digest(signature, expected_signature)



async def send_reply(reply_token: str, messages: list[dict]):
    """ส่งข้อความตอบกลับผ่าน Reply API."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    payload = {
        "replyToken": reply_token,
        "messages": messages,
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(LINE_REPLY_URL, headers=headers, json=payload)
        if response.status_code != 200:
            logger.error(f"Reply failed: {response.status_code} - {response.text}")
        else:
            logger.info("Reply sent successfully")


async def send_push(user_id: str, messages: list[dict]):
    """ส่งข้อความผ่าน Push API."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    payload = {
        "to": user_id,
        "messages": messages,
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(LINE_PUSH_URL, headers=headers, json=payload)
        if response.status_code != 200:
            logger.error(f"Push failed: {response.status_code} - {response.text}")
        else:
            logger.info("Push sent successfully")


async def get_line_display_name(user_id: str) -> str:
    """ดึง display name ของลูกค้าจาก LINE Messaging API."""
    try:
        headers = {
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{LINE_API_BASE}/profile/{user_id}",
                headers=headers,
            )
            if response.status_code == 200:
                data = response.json()
                display_name = data.get("displayName", user_id)
                logger.info(f"Got display name for {user_id}: {display_name}")
                return display_name
            else:
                logger.warning(f"Could not get display name for {user_id}: {response.status_code}")
                return user_id
    except Exception as e:
        logger.error(f"Error getting display name for {user_id}: {e}")
        return user_id


async def send_telegram_notification(user_id: str, customer_message: str, is_urgent: bool = False):
    """ส่งแจ้งเตือน Telegram เมื่อ AI ตอบลูกค้า พร้อมปุ่ม 'รับเรื่องแล้ว'."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not configured, skipping notification")
        return
    
    try:
        # ดึง display name จาก LINE API (ถ้าไม่ได้จะ fallback เป็น user_id)
        display_name = await get_line_display_name(user_id)
        
        # สร้างข้อความแจ้งเตือน (แยกรูปแบบตามประเภท)
        if is_urgent:
            notification_text = (
                f"🚨 ด่วน! ลูกค้าไม่พอใจ\n"
                f"ชื่อ: {display_name}\n"
                f"ข้อความ: {customer_message}\n"
                f"AI ตอบแล้ว - รอดำเนินการ"
            )
        else:
            notification_text = (
                f"🔔 มีลูกค้าทักมา\n"
                f"ชื่อ: {display_name}\n"
                f"ข้อความ: {customer_message}\n"
                f"AI ตอบแล้ว - รอดำเนินการ"
            )
        
        # Inline Keyboard ปุ่ม "รับเรื่องแล้ว" พร้อม user_id ใน callback_data
        reply_markup = {
            "inline_keyboard": [
                [
                    {
                        "text": "✅ รับเรื่องแล้ว",
                        "callback_data": f"ack:{user_id}",
                    }
                ]
            ]
        }
        
        # เรียก Telegram Bot API sendMessage
        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": notification_text,
            "reply_markup": reply_markup,
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(telegram_url, json=payload)
            if response.status_code != 200:
                logger.error(f"Telegram notification failed: {response.status_code} - {response.text}")
            else:
                logger.info(f"Telegram notification sent for {display_name} (urgent={is_urgent})")
    except Exception as e:
        logger.error(f"Error sending Telegram notification: {e}")


async def mark_chat_as_follow_up(user_id: str):
    """
    เปลี่ยนสถานะแชทเป็น "ต้องดำเนินการ" (Follow Up)
    
    หมายเหตุ: LINE Official Account Manager ไม่มี Public API สำหรับเปลี่ยนสถานะแชทโดยตรง
    ดังนั้นเราจะ:
    1. บันทึกสถานะในระบบของเราเอง (เพื่อให้ bot ไม่ตอบซ้ำ)
    2. ใช้ LINE OA Manager Chat Tag API (ถ้ามี) หรือ manual process
    
    สำหรับ LINE OA ที่ใช้ Module Channel (LINE Marketplace):
    - สามารถใช้ Acquire Control API / Release Control API ได้
    
    สำหรับ LINE OA ปกติ:
    - ใช้ internal state tracking ในระบบของเรา
    - แนะนำให้ใช้ร่วมกับ LINE OA Manager manual tagging
    """
    # บันทึกสถานะในระบบ
    state_manager.set_status(user_id, "follow_up")
    logger.info(f"Chat marked as follow-up for user: {user_id}")
    
    # พยายามใช้ LINE OA Chat API (undocumented/internal)
    # Endpoint นี้อาจใช้ได้กับบาง LINE OA ที่เปิดใช้งาน Chat feature
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        }
        # ลองเรียก mark as read เพื่อให้ admin เห็นว่า bot จัดการแล้ว
        payload = {"chatId": user_id}
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{LINE_API_BASE}/chat/markAsRead",
                headers=headers,
                json=payload,
            )
            logger.info(f"Mark as read response: {response.status_code}")
    except Exception as e:
        logger.warning(f"Could not mark as read via API: {e}")


# =============================================================================
# Message Classification using OpenAI
# =============================================================================


CLASSIFICATION_PROMPT = """คุณเป็นระบบจำแนกประเภทข้อความจากลูกค้าที่ทักมาใน LINE OA
จงวิเคราะห์ข้อความและจำแนกเป็น 1 ใน 3 กรณี:

กรณีที่ 1 (greeting): ลูกค้าส่งสติ๊กเกอร์, พิมพ์ผิดอ่านไม่รู้เรื่อง, ทักทาย, สนใจ, สวัสดี, หวัดดี, ดีครับ, ดีค่ะ, สนใจ, อยากรู้, ข้อมูล, หรือข้อความทั่วไปที่ไม่ชัดเจน

กรณีที่ 2 (transaction): ข้อความเกี่ยวกับการทำรายการ มีคีย์เวิร์ด เช่น ฝาก, ถอน, เล่นเกม, เกม, ค้าง, รอนาน, นาน, โอน, เติม, สมัคร, ยูสเซอร์, user, เครดิต, โบนัส, ฝากเงิน, ถอนเงิน

กรณีที่ 3 (angry): ข้อความที่มีคำด่า คำหยาบ แสดงอารมณ์โกรธ เช่น ไม่แตก, ควย, เหี้ย, สัตว์, ห่า, แม่ง, เชี่ย, กาก, ห่วย, โกง, หลอก, มึง, กู, ไอ้, อี, บ้า, เลว, ชิบ, สัส, หมา, ควาย หรือคำด่าอื่นๆ

ตอบเป็น JSON format เท่านั้น:
{"category": "greeting" | "transaction" | "angry"}

ข้อความจากลูกค้า: """


ANGRY_RESPONSE_PROMPT = """คุณคือ "ลินดา" พนักงานบริการลูกค้าผู้หญิง พูดจาน่ารัก ขี้อ้อน สุภาพ
ลูกค้ากำลังหัวร้อนและด่ามา คุณต้องตอบแบบปลอบอารมณ์ ขอโทษ และรีบจัดการให้
ตอบสั้นๆ 1-2 ประโยค ใช้คำลงท้าย "ค่ะ" หรือ "คะ" 
สไตล์ขี้อ้อนแต่มืออาชีพ เช่น:
- "ขอโทษด้วยนะคะพี่ เดี๋ยวลินดาจะรีบแก้ไขให้ค่ะ"
- "อย่าด่าหนูเลยค่ะพี่ เดี๋ยวหนูรีบจัดการให้เลยนะคะ"
- "พี่อย่าโกรธหนูเลยนะคะ เดี๋ยวหนูรีบดูให้เลยค่ะ"

ห้ามพูดว่าเป็น AI หรือ bot ห้ามพูดถึงเทคโนโลยี ตอบเหมือนคนจริงๆ

ข้อความจากลูกค้า: """


async def classify_message(text: str) -> str:
    """จำแนกประเภทข้อความโดยใช้ OpenAI GPT."""
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {"role": "system", "content": "You are a message classifier. Respond only in JSON."},
                {"role": "user", "content": CLASSIFICATION_PROMPT + text},
            ],
            temperature=0.1,
            max_tokens=50,
        )
        result = response.choices[0].message.content.strip()
        # Parse JSON response
        parsed = json.loads(result)
        category = parsed.get("category", "greeting")
        if category not in ["greeting", "transaction", "angry"]:
            category = "greeting"
        logger.info(f"Message classified as: {category}")
        return category
    except Exception as e:
        logger.error(f"Classification error: {e}")
        # Default to greeting if classification fails
        return "greeting"


async def generate_angry_response(text: str) -> str:
    """สร้างข้อความตอบกลับสำหรับลูกค้าที่โกรธ."""
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {"role": "system", "content": "คุณคือลินดา พนักงานบริการลูกค้า ตอบสั้นๆ น่ารัก ขี้อ้อน"},
                {"role": "user", "content": ANGRY_RESPONSE_PROMPT + text},
            ],
            temperature=0.7,
            max_tokens=100,
        )
        result = response.choices[0].message.content.strip()
        logger.info(f"Generated angry response: {result}")
        return result
    except Exception as e:
        logger.error(f"Response generation error: {e}")
        return "ขอโทษด้วยนะคะพี่ เดี๋ยวลินดาจะรีบแก้ไขให้ค่ะ"


# =============================================================================
# Webhook Handler
# =============================================================================


async def handle_message_event(event: dict):
    """จัดการ message event จาก LINE webhook."""
    user_id = event["source"]["userId"]
    reply_token = event["replyToken"]
    message = event.get("message", {})
    message_type = message.get("type", "")
    
    # ใช้ per-user lock เพื่อป้องกัน race condition กรณี LINE ส่ง event ซ้ำหรือพร้อมกัน
    lock = get_user_lock(user_id)
    async with lock:
        # เช็ค inactivity timeout: ถ้าลูกค้าหายไปเกิน 30 นาที ให้ reset สถานะเพื่อให้ AI ตอบได้ใหม่
        was_reset = state_manager.check_and_reset_if_inactive(user_id)
        if was_reset:
            logger.info(f"User {user_id} returned after inactivity - status reset, AI will respond again")
        
        # อัปเดต timestamp ของข้อความล่าสุด
        state_manager.update_last_activity(user_id)
        
        # ตรวจสอบสถานะแชท - ถ้ามีสถานะอยู่แล้ว ไม่ต้องตอบ
        current_status = state_manager.get_status(user_id)
        if current_status in ["follow_up", "resolved"]:
            logger.info(f"User {user_id} already has status '{current_status}', skipping.")
            return
        
        # กรณีเป็น sticker → จัดเป็นกรณีที่ 1 (greeting)
        if message_type == "sticker":
            logger.info(f"Sticker received from {user_id}")
            await handle_greeting(reply_token, user_id, "สติ๊กเกอร์")
            return
        
        # กรณีเป็น text message
        if message_type == "text":
            text = message.get("text", "").strip()
            logger.info(f"Text received from {user_id}: {text}")
            
            if not text:
                await handle_greeting(reply_token, user_id, "ข้อความว่าง")
                return
            
            # ตรวจสอบคีย์เวิร์ดก่อน (เร็วกว่า API call)
            category = check_keywords(text)
            
            # ถ้าไม่ match คีย์เวิร์ด ใช้ AI จำแนก
            if category is None:
                category = await classify_message(text)
            
            # จัดการตามประเภท
            if category == "greeting":
                await handle_greeting(reply_token, user_id, text)
            elif category == "transaction":
                await handle_transaction(reply_token, user_id, text)
            elif category == "angry":
                await handle_angry(reply_token, user_id, text)
            else:
                await handle_greeting(reply_token, user_id, text)
            return
        
        # กรณีอื่นๆ (image, video, audio, location, etc.) → จัดเป็น greeting
        logger.info(f"Other message type '{message_type}' from {user_id}")
        await handle_greeting(reply_token, user_id, f"{message_type} message")


def check_keywords(text: str) -> str | None:
    """ตรวจสอบคีย์เวิร์ดแบบ rule-based (เร็วกว่า AI)."""
    text_lower = text.lower()
    
    # คีย์เวิร์ดกรณีที่ 2 (transaction)
    transaction_keywords = [
        "ฝาก", "ถอน", "เล่นเกม", "เกม", "ค้าง", "รอนาน", "นาน",
        "โอน", "เติม", "สมัคร", "ยูสเซอร์", "user", "เครดิต", "โบนัส",
        "ฝากเงิน", "ถอนเงิน", "โปรโมชั่น", "โปร", "ทำรายการ",
    ]
    
    # คีย์เวิร์ดกรณีที่ 3 (angry/คำด่า)
    angry_keywords = [
        "ไม่แตก", "ควย", "เหี้ย", "สัตว์", "ห่า", "แม่ง", "เชี่ย",
        "กาก", "ห่วย", "โกง", "หลอก", "มึง", "กู", "ไอ้", "อี",
        "บ้า", "เลว", "ชิบ", "สัส", "หมา", "ควาย", "เย็ด", "หี",
        "แดก", "ตอแหล", "ระยำ", "ชาติหมา", "กระหรี่", "อีดอก",
        "อีสัตว์", "ไอ้สัตว์", "เวร", "กรรม", "ทุเรศ",
    ]
    
    # ตรวจ angry ก่อน (priority สูงกว่า)
    for keyword in angry_keywords:
        if keyword in text_lower:
            return "angry"
    
    # ตรวจ transaction
    for keyword in transaction_keywords:
        if keyword in text_lower:
            return "transaction"
    
    # ไม่ match → return None ให้ AI จำแนก
    return None


async def handle_greeting(reply_token: str, user_id: str, customer_message: str = "สติ๊กเกอร์/ทักทาย"):
    """กรณีที่ 1: ทักทาย / สติ๊กเกอร์ / ข้อความทั่วไป."""
    messages = [
        {"type": "text", "text": "สวัสดีคะพี่ หนูลินดายินดีให้บริการ"},
        {
            "type": "text",
            "text": "ไม่ทราบว่าคุณพี่ต้องการทำรายการด้านใดคะ",
            "quickReply": {
                "items": [
                    {
                        "type": "action",
                        "action": {
                            "type": "message",
                            "label": "💰 ฝากเงิน",
                            "text": "ฝากเงิน",
                        },
                    },
                    {
                        "type": "action",
                        "action": {
                            "type": "message",
                            "label": "💸 ถอนเงิน",
                            "text": "ถอนเงิน",
                        },
                    },
                    {
                        "type": "action",
                        "action": {
                            "type": "message",
                            "label": "🎮 เล่นเกม",
                            "text": "เล่นเกม",
                        },
                    },
                    {
                        "type": "action",
                        "action": {
                            "type": "message",
                            "label": "👩‍💼 ติดต่อแอดมิน",
                            "text": "ติดต่อแอดมิน",
                        },
                    },
                ]
            },
        },
    ]
    await send_reply(reply_token, messages)
    await mark_chat_as_follow_up(user_id)
    # ส่งแจ้งเตือน Telegram
    await send_telegram_notification(user_id, customer_message)
    logger.info(f"[Case 1 - Greeting] Handled for user: {user_id}")


async def handle_transaction(reply_token: str, user_id: str, customer_message: str = ""):
    """กรณีที่ 2: ฝาก/ถอน/เกม/ค้าง/รอนาน."""
    messages = [
        {"type": "text", "text": "รอสักครู่นะคะ น้องลินดาจะรีบทำรายการใหสักครู่"},
    ]
    await send_reply(reply_token, messages)
    await mark_chat_as_follow_up(user_id)
    # ส่งแจ้งเตือน Telegram
    await send_telegram_notification(user_id, customer_message)
    logger.info(f"[Case 2 - Transaction] Handled for user: {user_id}")


async def handle_angry(reply_token: str, user_id: str, text: str):
    """กรณีที่ 3: คำด่า / อารมณ์โกรธ."""
    response_text = await generate_angry_response(text)
    messages = [
        {"type": "text", "text": response_text},
    ]
    await send_reply(reply_token, messages)
    await mark_chat_as_follow_up(user_id)
    # ส่งแจ้งเตือน Telegram แบบ urgent (สำหรับลูกค้าโกรธ)
    await send_telegram_notification(user_id, text, is_urgent=True)
    logger.info(f"[Case 3 - Angry] Handled for user: {user_id}")


# =============================================================================
# API Routes
# =============================================================================


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "bot_name": "ลินดา",
        "version": "1.0.0",
        "description": "Line OA Chatbot - AI Customer Service",
    }


@app.get("/health")
async def health():
    """Health check for Railway."""
    return {"status": "healthy"}


@app.post("/webhook")
async def webhook(request: Request):
    """LINE Webhook endpoint - รับ events จาก LINE Platform."""
    # อ่าน body
    body = await request.body()
    
    # ตรวจสอบ signature
    signature = request.headers.get("X-Line-Signature", "")
    if not signature:
        raise HTTPException(status_code=400, detail="Missing signature")
    
    if not verify_signature(body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")
    
    # Parse events
    try:
        data = json.loads(body)
        events = data.get("events", [])
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    # Process events
    for event in events:
        event_type = event.get("type", "")
        
        if event_type == "message":
            await handle_message_event(event)
        elif event_type == "follow":
            # ลูกค้า add friend → ignore ไม่ตอบอัตโนมัติ
            user_id = event["source"]["userId"]
            logger.info(f"Follow event received for {user_id} - ignored (no auto-reply)")
        elif event_type == "unfollow":
            # ลูกค้า block → ลบสถานะออก
            user_id = event["source"]["userId"]
            state_manager.remove_user(user_id)
            logger.info(f"Unfollow event received for {user_id} - status cleared")
        else:
            logger.info(f"Unhandled event type: {event_type} - ignored")
    
    return JSONResponse(content={"status": "ok"}, status_code=200)


@app.post("/reset-status/{user_id}")
async def reset_status(user_id: str):
    """
    Reset สถานะแชทของ user (สำหรับ admin ใช้)
    เรียก endpoint นี้เมื่อ admin จัดการเคสเสร็จแล้ว
    เพื่อให้ bot สามารถตอบลูกค้าคนนี้ได้อีกครั้ง
    """
    state_manager.remove_user(user_id)
    return {"status": "ok", "message": f"Status reset for user: {user_id}"}


@app.post("/reset-all")
async def reset_all():
    """Reset สถานะแชททั้งหมด (สำหรับ admin)."""
    state_manager.reset_all()
    return {"status": "ok", "message": "All statuses reset"}


@app.get("/status/{user_id}")
async def get_status(user_id: str):
    """ดูสถานะแชทของ user."""
    status = state_manager.get_status(user_id)
    return {"user_id": user_id, "status": status}


@app.get("/stats")
async def get_stats():
    """ดูสถิติ."""
    return state_manager.get_stats()


@app.post("/telegram/callback")
async def telegram_callback(request: Request):
    """
    Telegram Webhook endpoint - รับ callback_query จาก Telegram Bot
    เมื่อแอดมินกดปุ่ม '✅ รับเรื่องแล้ว' ใน Telegram
    """
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(content={"status": "ok"}, status_code=200)

    # จัดการเฉพาะ callback_query (การกดปุ่ม)
    callback_query = data.get("callback_query")
    if not callback_query:
        # ไม่ใช่ callback อาจเป็น message อื่นๆ ไม่ต้องทำอะไร
        return JSONResponse(content={"status": "ok"}, status_code=200)

    callback_id = callback_query.get("id", "")
    callback_data = callback_query.get("data", "")
    from_user = callback_query.get("from", {})
    admin_name = from_user.get("first_name", "")
    admin_last = from_user.get("last_name", "")
    admin_full = f"{admin_name} {admin_last}".strip() or "Admin"
    message = callback_query.get("message", {})
    message_id = message.get("message_id")
    chat_id = message.get("chat", {}).get("id")
    original_text = message.get("text", "")

    # ตรวจสอบว่าเป็น callback ประเภท ack:{user_id}
    if callback_data.startswith("ack:"):
        line_user_id = callback_data[4:]  # ตัด "ack:" ออก
        logger.info(f"Admin '{admin_full}' acknowledged case for LINE user: {line_user_id}")

        # เปลี่ยนสถานะ LINE chat เป็น resolved
        state_manager.set_status(line_user_id, "resolved")

        # แก้ไขข้อความเดิมใน Telegram ให้แสดงว่ารับเรื่องแล้ว
        updated_text = f"{original_text}\n\n✅ รับเรื่องแล้ว โดย {admin_full}"
        try:
            async with httpx.AsyncClient() as client:
                # แก้ไขข้อความเดิม (editMessageText)
                edit_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText"
                edit_payload = {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": updated_text,
                    "reply_markup": {"inline_keyboard": []},  # ลบปุ่มออก
                }
                edit_resp = await client.post(edit_url, json=edit_payload)
                if edit_resp.status_code != 200:
                    logger.warning(f"editMessageText failed: {edit_resp.status_code} - {edit_resp.text}")

                # ตอบกลับ Telegram ว่ารับ callback แล้ว (หยุด loading indicator)
                answer_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
                await client.post(answer_url, json={
                    "callback_query_id": callback_id,
                    "text": "✅ รับเรื่องแล้ว!",
                })
        except Exception as e:
            logger.error(f"Error updating Telegram message: {e}")
    else:
        # callback ประเภทอื่น ตอบกลับเพื่อหยุด loading indicator
        try:
            async with httpx.AsyncClient() as client:
                answer_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
                await client.post(answer_url, json={"callback_query_id": callback_id})
        except Exception:
            pass

    return JSONResponse(content={"status": "ok"}, status_code=200)


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
