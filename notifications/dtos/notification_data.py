# ============================================================================
# DTOs - Data Transfer Objects
# ============================================================================

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class NotificationData:
    """DTO para datos de notificación"""

    event_code: str
    user_id: int
    context: Dict[str, Any]
    uuid: Optional[str] = None
    scheduled_for: Optional[datetime] = None
