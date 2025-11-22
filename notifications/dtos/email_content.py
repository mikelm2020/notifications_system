# ============================================================================
# DTOs - Data Transfer Objects
# ============================================================================

from dataclasses import dataclass
from typing import Optional


@dataclass
class EmailContent:
    """DTO para contenido de email."""

    subject: str
    body: str
    to_email: str
    from_email: Optional[str] = None
    html_body: Optional[str] = None
    reply_to: Optional[str] = None
