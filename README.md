# Line OA Chatbot - "ลินดา" 🤖

AI Chatbot สำหรับ Line Official Account พัฒนาด้วย Python (FastAPI) และ OpenAI GPT
ออกแบบมาเพื่อทำงานร่วมกับแอดมิน (มนุษย์) โดย AI จะช่วยคัดกรองและตอบกลับลูกค้าเบื้องต้น

## 🌟 ฟีเจอร์หลัก

1. **ระบบคัดกรองแชทอัจฉริยะ**: AI จะตอบเฉพาะแชทที่ "ไม่มีสถานะ" เท่านั้น หากแชทไหนแอดมินกำลังดูแลอยู่ (มีสถานะ "ต้องดำเนินการ" หรือ "เสร็จสิ้น") AI จะไม่เข้าไปยุ่ง
2. **จำแนกข้อความ 3 กรณี**:
   - **กรณีที่ 1 (ทักทาย/ทั่วไป)**: ตอบกลับด้วยข้อความต้อนรับ "สวัสดีคะพี่ หนูลินดายินดีให้บริการ" และถามความต้องการ
   - **กรณีที่ 2 (ทำรายการ)**: ตรวจจับคีย์เวิร์ด (ฝาก, ถอน, เล่นเกม ฯลฯ) และตอบกลับ "รอสักครู่นะคะ น้องลินดาจะรีบทำรายการให้สักครู่"
   - **กรณีที่ 3 (หัวร้อน/คำด่า)**: ใช้ OpenAI GPT วิเคราะห์และสร้างคำตอบสไตล์ขี้อ้อน ปลอบใจลูกค้า เช่น "ขอโทษด้วยนะคะพี่ เดี๋ยวลินดาจะรีบแก้ไขให้ค่ะ"
3. **เปลี่ยนสถานะแชทอัตโนมัติ**: เมื่อ AI ตอบกลับแล้ว จะเปลี่ยนสถานะแชทเป็น "ต้องดำเนินการ" (Follow-up) ทันที เพื่อส่งต่อให้แอดมินจัดการต่อ

> **หมายเหตุเรื่อง API สถานะแชท**: ปัจจุบัน LINE Official Account Manager ไม่มี Public API สำหรับเปลี่ยนสถานะแชท ("ต้องดำเนินการ" / "เสร็จสิ้น") โดยตรง ระบบนี้จึงใช้การจำลองสถานะ (State Tracking) ภายในตัว Bot เอง เพื่อให้ Bot รู้ว่าแชทไหนจัดการแล้วและไม่ควรเข้าไปตอบซ้ำ

---

## 🚀 วิธีการ Deploy บน Railway

โปรเจคนี้เตรียมไฟล์คอนฟิกสำหรับ Railway ไว้เรียบร้อยแล้ว (`railway.toml`, `nixpacks.toml`, `Procfile`)

### ขั้นตอนที่ 1: เตรียมบัญชีและ API Keys
1. **LINE Official Account**:
   - ไปที่ [LINE Developers Console](https://developers.line.biz/)
   - สร้าง Provider และ Messaging API Channel
   - คัดลอก `Channel access token (long-lived)` และ `Channel secret`
2. **OpenAI**:
   - ไปที่ [OpenAI API Keys](https://platform.openai.com/api-keys)
   - สร้าง API Key ใหม่
3. **Railway**:
   - สมัครบัญชี [Railway](https://railway.app/) (สามารถผูกกับ GitHub ได้)

### ขั้นตอนที่ 2: อัปโหลดโค้ดขึ้น GitHub
1. สร้าง Repository ใหม่บน GitHub
2. อัปโหลดไฟล์ทั้งหมดในโฟลเดอร์นี้ขึ้น Repository

### ขั้นตอนที่ 3: Deploy บน Railway
1. ล็อกอินเข้า Railway คลิก **"New Project"**
2. เลือก **"Deploy from GitHub repo"**
3. เลือก Repository ที่เพิ่งสร้าง
4. ไปที่แท็บ **"Variables"** และเพิ่ม Environment Variables ดังนี้:
   - `LINE_CHANNEL_ACCESS_TOKEN` = (ค่าจาก LINE Developers)
   - `LINE_CHANNEL_SECRET` = (ค่าจาก LINE Developers)
   - `OPENAI_API_KEY` = (ค่าจาก OpenAI)
5. Railway จะทำการ Build และ Deploy อัตโนมัติ (ใช้เวลาประมาณ 1-2 นาที)
6. ไปที่แท็บ **"Settings"** > **"Networking"** > **"Generate Domain"** เพื่อสร้าง URL สำหรับ Webhook

### ขั้นตอนที่ 4: ตั้งค่า Webhook ใน LINE
1. กลับไปที่ LINE Developers Console
2. ไปที่แท็บ **"Messaging API"**
3. ตรงหัวข้อ **Webhook settings** ให้ใส่ URL ที่ได้จาก Railway ตามด้วย `/webhook`
   - ตัวอย่าง: `https://your-app-name.up.railway.app/webhook`
4. กด **"Verify"** (ต้องขึ้น Success)
5. เปิดใช้งาน **"Use webhook"**
6. ปิดการใช้งาน **"Auto-response messages"** ใน LINE Official Account Manager

---

## 🛠️ การจัดการสถานะแชท (สำหรับแอดมิน)

เนื่องจากเราใช้ระบบ State Tracking ภายใน เมื่อแอดมินจัดการเคสของลูกค้าเสร็จแล้ว และต้องการให้ AI กลับมาตอบลูกค้าคนนี้ในครั้งต่อไป แอดมินสามารถ Reset สถานะได้ 2 วิธี:

1. **รอหมดอายุอัตโนมัติ**: ระบบตั้งค่าให้สถานะหมดอายุอัตโนมัติใน 24 ชั่วโมง
2. **เรียก API Reset**: 
   - Reset รายบุคคล: `POST https://your-app-name.up.railway.app/reset-status/{user_id}`
   - Reset ทั้งหมด: `POST https://your-app-name.up.railway.app/reset-all`

---

## 📁 โครงสร้างไฟล์

- `app.py`: ไฟล์หลักของแอปพลิเคชัน (FastAPI, Webhook, AI Logic)
- `chat_state.py`: ระบบจัดการสถานะแชท (State Manager)
- `requirements.txt`: รายชื่อไลบรารี Python ที่ต้องใช้
- `Procfile` / `railway.toml` / `nixpacks.toml`: ไฟล์ตั้งค่าสำหรับ Deploy บน Railway
- `runtime.txt`: กำหนดเวอร์ชัน Python (3.11)
- `.env.example`: ตัวอย่างไฟล์ Environment Variables
