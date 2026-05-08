"""
Line OA Chatbot - "ลินดา"
AI Chatbot สำหรับ Line Official Account
ใช้ FastAPI + Line Messaging API + OpenAI GPT
"""

import os
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


async def send_telegram_notification(display_name: str, customer_message: str):
    """ส่งแจ้งเตือน Telegram เมื่อ AI ตอบลูกค้า."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not configured, skipping notification")
        return
    
    try:
        # สร้างข้อความแจ้งเตือน
        notification_text = (
            f"🔔 มีลูกค้าทักมา\n"
            f"ชื่อ: {display_name}\n"
            f"ข้อความ: {customer_message}\n"
            f"AI ตอบแล้ว - รอดำเนินการ"
        )
        
        # เรียก Telegram Bot API
        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": notification_text,
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(telegram_url, json=payload)
            if response.status_code != 200:
                logger.error(f"Telegram notification failed: {response.status_code} - {response.text}")
            else:
                logger.info(f"Telegram notification sent successfully")
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
        {"type": "text", "text": "ไม่ทราบว่าคุณพี่ต้องการทำรายการด้านใดคะ"},
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
    # ส่งแจ้งเตือน Telegram
    await send_telegram_notification(user_id, text)
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
            # ลูกค้า add friend
            user_id = event["source"]["userId"]
            reply_token = event["replyToken"]
            logger.info(f"New follower: {user_id}")
            # ส่งข้อความต้อนรับ
            messages = [
                {"type": "text", "text": "สวัสดีคะพี่ หนูลินดายินดีให้บริการ"},
                {"type": "text", "text": "ไม่ทราบว่าคุณพี่ต้องการทำรายการด้านใดคะ"},
            ]
            await send_reply(reply_token, messages)
        elif event_type == "unfollow":
            # ลูกค้า block
            user_id = event["source"]["userId"]
            state_manager.remove_user(user_id)
            logger.info(f"User unfollowed: {user_id}")
        else:
            logger.info(f"Unhandled event type: {event_type}")
    
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


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
