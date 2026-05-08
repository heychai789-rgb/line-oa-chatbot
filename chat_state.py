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
"""

import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ChatStateManager:
    """จัดการสถานะแชทของลูกค้า."""

    def __init__(self, auto_expire_hours: int = 24):
        """
        Initialize ChatStateManager.
        
        Args:
            auto_expire_hours: จำนวนชั่วโมงที่สถานะจะหมดอายุอัตโนมัติ
                              (เพื่อให้ bot กลับมาตอบได้ถ้า admin ลืม reset)
        """
        self._states: dict[str, dict] = {}
        self._auto_expire_seconds = auto_expire_hours * 3600
        logger.info(f"ChatStateManager initialized (auto-expire: {auto_expire_hours}h)")

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
        
        # ตรวจสอบว่าหมดอายุหรือยัง
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

    def reset_all(self):
        """Reset สถานะทั้งหมด."""
        count = len(self._states)
        self._states.clear()
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
        }
