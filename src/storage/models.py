"""
Persistent state storage models.

These models track the sync state between Canvas and Outlook.
"""

from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional


@dataclass
class SyncState:
    """
    Represents the synchronized state of a Canvas assignment.
    
    This record tracks:
    - The Canvas assignment identity (course_id + assignment_id)
    - The corresponding Outlook task ID
    - Last known state for diff detection
    
    Attributes:
        canvas_course_id: Canvas course identifier
        canvas_assignment_id: Canvas assignment identifier
        outlook_task_id: Microsoft Graph task ID (None if not yet synced)
        last_seen_submission_state: "submitted" or "not_submitted"
        last_seen_due_date: Due date from last sync (as ISO string)
        last_seen_title: Assignment title from last sync
        last_synced_at: Timestamp of last successful sync
        is_archived: Whether assignment was deleted/archived
        created_at: When this record was created
    """
    canvas_course_id: int
    canvas_assignment_id: int
    outlook_task_id: Optional[str] = None
    last_seen_submission_state: str = "not_submitted"
    last_seen_due_date: Optional[str] = None  # ISO format date string
    last_seen_title: str = ""
    last_synced_at: Optional[datetime] = None
    is_archived: bool = False
    created_at: Optional[datetime] = None
    
    @property
    def unique_key(self) -> tuple[int, int]:
        """Return the unique Canvas identifier."""
        return (self.canvas_course_id, self.canvas_assignment_id)
    
    @property
    def is_synced(self) -> bool:
        """Check if this assignment has been synced to Outlook."""
        return self.outlook_task_id is not None
    
    @property
    def was_submitted(self) -> bool:
        """Check if assignment was previously marked as submitted."""
        return self.last_seen_submission_state == "submitted"
    
    @property
    def due_date_as_date(self) -> Optional[date]:
        """Parse the due date string to a date object."""
        if self.last_seen_due_date:
            return date.fromisoformat(self.last_seen_due_date)
        return None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "canvas_course_id": self.canvas_course_id,
            "canvas_assignment_id": self.canvas_assignment_id,
            "outlook_task_id": self.outlook_task_id,
            "last_seen_submission_state": self.last_seen_submission_state,
            "last_seen_due_date": self.last_seen_due_date,
            "last_seen_title": self.last_seen_title,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
            "is_archived": self.is_archived,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SyncState":
        """Create from dictionary."""
        last_synced = None
        if data.get("last_synced_at"):
            last_synced = datetime.fromisoformat(data["last_synced_at"])
        
        created = None
        if data.get("created_at"):
            created = datetime.fromisoformat(data["created_at"])
        
        return cls(
            canvas_course_id=data["canvas_course_id"],
            canvas_assignment_id=data["canvas_assignment_id"],
            outlook_task_id=data.get("outlook_task_id"),
            last_seen_submission_state=data.get("last_seen_submission_state", "not_submitted"),
            last_seen_due_date=data.get("last_seen_due_date"),
            last_seen_title=data.get("last_seen_title", ""),
            last_synced_at=last_synced,
            is_archived=data.get("is_archived", False),
            created_at=created,
        )
    
    @classmethod
    def from_row(cls, row: tuple) -> "SyncState":
        """Create from SQLite row tuple."""
        (
            canvas_course_id,
            canvas_assignment_id,
            outlook_task_id,
            last_seen_submission_state,
            last_seen_due_date,
            last_seen_title,
            last_synced_at,
            is_archived,
            created_at,
        ) = row
        
        last_synced = None
        if last_synced_at:
            last_synced = datetime.fromisoformat(last_synced_at)
        
        created = None
        if created_at:
            created = datetime.fromisoformat(created_at)
        
        return cls(
            canvas_course_id=canvas_course_id,
            canvas_assignment_id=canvas_assignment_id,
            outlook_task_id=outlook_task_id,
            last_seen_submission_state=last_seen_submission_state or "not_submitted",
            last_seen_due_date=last_seen_due_date,
            last_seen_title=last_seen_title or "",
            last_synced_at=last_synced,
            is_archived=bool(is_archived),
            created_at=created,
        )
