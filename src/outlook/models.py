"""
Microsoft Graph / Outlook Tasks data models.

These models represent Outlook Tasks and Task Lists.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional
from enum import Enum


class TaskStatus(Enum):
    """Outlook task status values."""
    NOT_STARTED = "notStarted"
    IN_PROGRESS = "inProgress"
    COMPLETED = "completed"
    WAITING_ON_OTHERS = "waitingOnOthers"
    DEFERRED = "deferred"


class TaskImportance(Enum):
    """Outlook task importance levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


@dataclass(frozen=True)
class TaskList:
    """
    Represents an Outlook Task List.
    
    Attributes:
        id: Microsoft Graph ID for the task list
        display_name: Name of the task list
        is_owner: Whether current user owns this list
        is_shared: Whether this list is shared
    """
    id: str
    display_name: str
    is_owner: bool = True
    is_shared: bool = False
    
    @classmethod
    def from_api_response(cls, data: dict) -> "TaskList":
        """Create TaskList from Microsoft Graph API response."""
        return cls(
            id=data["id"],
            display_name=data.get("displayName", ""),
            is_owner=data.get("isOwner", True),
            is_shared=data.get("isShared", False),
        )


@dataclass
class OutlookTask:
    """
    Represents an Outlook Task (Microsoft To Do).
    
    Attributes:
        id: Microsoft Graph ID (None for new tasks)
        title: Task title
        body_content: Task body/notes (plain text or HTML)
        due_date: Due date (date only, no time)
        status: Task completion status
        importance: Task importance level
        categories: List of category names
    """
    title: str
    body_content: str = ""
    due_date: Optional[date] = None
    status: TaskStatus = TaskStatus.NOT_STARTED
    importance: TaskImportance = TaskImportance.NORMAL
    categories: list[str] = field(default_factory=list)
    id: Optional[str] = None
    created_datetime: Optional[datetime] = None
    last_modified_datetime: Optional[datetime] = None
    completed_datetime: Optional[datetime] = None
    
    @property
    def is_completed(self) -> bool:
        """Check if task is marked as completed."""
        return self.status == TaskStatus.COMPLETED
    
    def to_api_payload(self) -> dict:
        """
        Convert to Microsoft Graph API payload for create/update.
        
        Returns:
            Dictionary suitable for JSON serialization
        """
        payload = {
            "title": self.title,
            "status": self.status.value,
            "importance": self.importance.value,
        }
        
        if self.body_content:
            payload["body"] = {
                "content": self.body_content,
                "contentType": "text",
            }
        
        if self.due_date:
            payload["dueDateTime"] = {
                "dateTime": f"{self.due_date.isoformat()}T00:00:00",
                "timeZone": "UTC",
            }
        
        if self.categories:
            payload["categories"] = self.categories
        
        return payload
    
    def to_update_payload(self, changes_only: dict) -> dict:
        """
        Create minimal update payload with only changed fields.
        
        Args:
            changes_only: Dictionary of field names to new values
            
        Returns:
            Minimal API payload for PATCH request
        """
        payload = {}
        
        if "title" in changes_only:
            payload["title"] = changes_only["title"]
        
        if "status" in changes_only:
            payload["status"] = changes_only["status"].value
        
        if "due_date" in changes_only:
            due = changes_only["due_date"]
            if due:
                payload["dueDateTime"] = {
                    "dateTime": f"{due.isoformat()}T00:00:00",
                    "timeZone": "UTC",
                }
            else:
                payload["dueDateTime"] = None
        
        if "body_content" in changes_only:
            payload["body"] = {
                "content": changes_only["body_content"],
                "contentType": "text",
            }
        
        return payload
    
    @classmethod
    def from_api_response(cls, data: dict) -> "OutlookTask":
        """Create OutlookTask from Microsoft Graph API response."""
        due_date = None
        if data.get("dueDateTime") and data["dueDateTime"].get("dateTime"):
            due_str = data["dueDateTime"]["dateTime"]
            # Handle both date and datetime formats
            if "T" in due_str:
                due_date = datetime.fromisoformat(due_str.replace("Z", "+00:00")).date()
            else:
                due_date = date.fromisoformat(due_str)
        
        created = None
        if data.get("createdDateTime"):
            created = datetime.fromisoformat(
                data["createdDateTime"].replace("Z", "+00:00")
            )
        
        modified = None
        if data.get("lastModifiedDateTime"):
            modified = datetime.fromisoformat(
                data["lastModifiedDateTime"].replace("Z", "+00:00")
            )
        
        completed = None
        if data.get("completedDateTime") and data["completedDateTime"].get("dateTime"):
            completed = datetime.fromisoformat(
                data["completedDateTime"]["dateTime"].replace("Z", "+00:00")
            )
        
        body_content = ""
        if data.get("body") and data["body"].get("content"):
            body_content = data["body"]["content"]
        
        return cls(
            id=data["id"],
            title=data.get("title", ""),
            body_content=body_content,
            due_date=due_date,
            status=TaskStatus(data.get("status", "notStarted")),
            importance=TaskImportance(data.get("importance", "normal")),
            categories=data.get("categories", []),
            created_datetime=created,
            last_modified_datetime=modified,
            completed_datetime=completed,
        )


@dataclass
class CanvasTaskMetadata:
    """
    Metadata embedded in task body to identify Canvas source.
    
    This is stored in the task notes/body to link back to Canvas.
    """
    canvas_course_id: int
    canvas_assignment_id: int
    canvas_url: str
    
    def to_body_content(self) -> str:
        """Generate body content string with metadata."""
        return (
            f"Canvas Assignment\n"
            f"================\n"
            f"Course ID: {self.canvas_course_id}\n"
            f"Assignment ID: {self.canvas_assignment_id}\n"
            f"URL: {self.canvas_url}\n"
            f"\n"
            f"---\n"
            f"Synced from Canvas LMS"
        )
    
    @classmethod
    def from_body_content(cls, content: str) -> Optional["CanvasTaskMetadata"]:
        """
        Parse metadata from task body content.
        
        Returns None if metadata cannot be parsed.
        """
        try:
            lines = content.strip().split("\n")
            course_id = None
            assignment_id = None
            url = ""
            
            for line in lines:
                if line.startswith("Course ID:"):
                    course_id = int(line.split(":", 1)[1].strip())
                elif line.startswith("Assignment ID:"):
                    assignment_id = int(line.split(":", 1)[1].strip())
                elif line.startswith("URL:"):
                    url = line.split(":", 1)[1].strip()
                    # Handle URLs that have : in them
                    if "://" not in url:
                        url = "https:" + url
            
            if course_id and assignment_id:
                return cls(
                    canvas_course_id=course_id,
                    canvas_assignment_id=assignment_id,
                    canvas_url=url,
                )
            return None
            
        except (ValueError, IndexError):
            return None
