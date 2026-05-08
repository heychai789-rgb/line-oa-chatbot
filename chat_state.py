"""
Chat State Manager
จัดการสถานะแชทของลูกค้าแต่ละคน

สถานะ:
- None: ไม่มีสถานะ (bot จะตอบ)
- "follow_up": ต้องดำเนินการ (bot จะไม่ตอบ - รอ admin)
- "resolved": เสร็จสิ้น (bot จะไม่ตอบ)

หมายเหตุ: 
- ใช้ in-memory storage (dict) สำหรับ prototype
- สำหรับ production แนะนำให้ใช้ Redis หรือ Database
- สถานะจะหายไปเมื่อ restart server (ซึ่งเป็นพฤติกรรมที่ต้องการ
  เพราะเมื่อ restart = reset ให้ bot ตอบลูกค้าได้ใหม่)

Inactivity Reset:
- ถ้าลูกค้าไม่ส่งข้อความมาเกิน inactivity_minutes (default 30 นาที)
  สถานะจะถูก reset อัตโนมัติเมื่อลูกค้าทักมาใหม่
- ทำให้ AI ตอบลูกค้าได้อีกครั้งเหมือนเริ่มต้นใหม่
"""

import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ChatStateManager:
    """จัดการสถานะแชทของลูกค้า."""

    def __init__(self, auto_expire_hours: int = 24, inactivity_minutes: int = 30):
        """
        Initialize ChatStateManager.
        
        Args:
            auto_expire_hours: จำนวนชั่วโมงที่สถานะจะหมดอายุอัตโนมัติ
                              (เพื่อให้ bot กลับมาตอบได้ถ้า admin ลืม reset)
            inactivity_minutes: จำนวนนาทีที่ถ้าไม่มีข้อความจะ reset สถานะอัตโนมัติ
                               (เพื่อให้ bot ตอบลูกค้าที่กลับมาทักใหม่หลังหายไปนาน)
        """
        self._states: dict[str, dict] = {}
        self._last_activity: dict[str, float] = {}
        self._auto_expire_seconds = auto_expire_hours * 3600
        self._inactivity_seconds = inactivity_minutes * 60
        logger.info(
            f"ChatStateManager initialized "
            f"(auto-expire: {auto_expire_hours}h, inactivity-reset: {inactivity_minutes}min)"
        )

    def check_and_reset_if_inactive(self, user_id: str) -> bool:
        """
        ตรวจสอบว่าลูกค้า inactive เกินกำหนดหรือไม่ ถ้าใช่ให้ reset สถานะ

        Returns:
            True ถ้าถูก reset (ลูกค้าหายไปนานแล้วกลับมา)
            False ถ้าไม่ได้ reset (ยังอยู่ในช่วง active)
        """
        if user_id not in self._last_activity:
            # ยังไม่เคยมีข้อความมาก่อน → ไม่ต้อง reset
            return False

        elapsed = time.time() - self._last_activity[user_id]
        if elapsed > self._inactivity_seconds:
            elapsed_min = int(elapsed // 60)
            logger.info(
                f"User {user_id} was inactive for {elapsed_min} min "
                f"(>{self._inactivity_seconds // 60} min threshold) - resetting status"
            )
            # Reset สถานะให้ bot ตอบได้ใหม่
            if user_id in self._states:
                del self._states[user_id]
            return True

        return False

    def update_last_activity(self, user_id: str):
        """อัปเดต timestamp ข้อความล่าสุดของ user."""
        self._last_activity[user_id] = time.time()

    def get_status(self, user_id: str) -> Optional[str]:
        """
        ดึงสถานะปัจจุบันของ user.
        
        Returns:
            None: ไม่มีสถานะ (bot ตอบได้)
            "follow_up": ต้องดำเนินการ
            "resolved": เสร็จสิ้น
        """
        if user_id not in self._states:
            return None
        
        state = self._states[user_id]
        
        # ตรวจสอบว่าหมดอายุหรือยัง (auto-expire รายวัน)
        if time.time() - state["timestamp"] > self._auto_expire_seconds:
            logger.info(f"Status expired for user: {user_id}")
            del self._states[user_id]
            return None
        
        return state["status"]

    def set_status(self, user_id: str, status: str):
        """
        ตั้งค่าสถานะของ user.
        
        Args:
            user_id: LINE user ID
            status: "follow_up" หรือ "resolved"
        """
        self._states[user_id] = {
            "status": status,
            "timestamp": time.time(),
        }
        logger.info(f"Status set for {user_id}: {status}")

    def remove_user(self, user_id: str):
        """ลบสถานะของ user (reset ให้ bot ตอบได้อีก)."""
        if user_id in self._states:
            del self._states[user_id]
            logger.info(f"Status removed for user: {user_id}")
        if user_id in self._last_activity:
            del self._last_activity[user_id]

    def reset_all(self):
        """Reset สถานะทั้งหมด."""
        count = len(self._states)
        self._states.clear()
        self._last_activity.clear()
        logger.info(f"All statuses reset ({count} entries cleared)")

    def get_stats(self) -> dict:
        """ดึงสถิติ."""
        total = len(self._states)
        follow_up = sum(1 for s in self._states.values() if s["status"] == "follow_up")
        resolved = sum(1 for s in self._states.values() if s["status"] == "resolved")
        return {
            "total_tracked": total,
            "follow_up": follow_up,
            "resolved": resolved,
            "auto_expire_hours": self._auto_expire_seconds / 3600,
            "inactivity_reset_minutes": self._inactivity_seconds / 60,
        }
