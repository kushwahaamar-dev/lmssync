"""
Canvas LMS data models.

These models represent the core entities fetched from Canvas API.
All IDs are integers from Canvas and form the primary identity.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Course:
    """
    Represents a Canvas course.
    
    Attributes:
        id: Unique Canvas course ID
        name: Course display name
        code: Course code (e.g., "CS101")
        enrollment_state: Current enrollment state (active, invited, etc.)
    """
    id: int
    name: str
    code: str
    enrollment_state: str
    
    def __post_init__(self):
        if not isinstance(self.id, int) or self.id <= 0:
            raise ValueError(f"Course ID must be a positive integer, got {self.id}")
    
    @classmethod
    def from_api_response(cls, data: dict) -> "Course":
        """Create Course from Canvas API response."""
        return cls(
            id=int(data["id"]),
            name=data.get("name", "Unknown Course"),
            code=data.get("course_code", ""),
            enrollment_state=data.get("enrollment_state", "unknown"),
        )


@dataclass(frozen=True)
class Submission:
    """
    Represents a user's submission for an assignment.
    
    Attributes:
        assignment_id: The assignment this submission is for
        submitted_at: Timestamp when submitted, None if not submitted
        workflow_state: State of submission (submitted, unsubmitted, graded, etc.)
        score: Grade score if graded
        grade: Grade string if graded
    """
    assignment_id: int
    submitted_at: Optional[datetime]
    workflow_state: str
    score: Optional[float] = None
    grade: Optional[str] = None
    
    @property
    def is_submitted(self) -> bool:
        """
        Check if assignment has been submitted.
        
        An assignment is considered submitted if:
        - submitted_at is not None, OR
        - workflow_state indicates submission (submitted, graded, pending_review)
        """
        if self.submitted_at is not None:
            return True
        return self.workflow_state in ("submitted", "graded", "pending_review")
    
    @classmethod
    def from_api_response(cls, data: dict) -> "Submission":
        """Create Submission from Canvas API response."""
        submitted_at = None
        if data.get("submitted_at"):
            submitted_at = datetime.fromisoformat(
                data["submitted_at"].replace("Z", "+00:00")
            )
        
        return cls(
            assignment_id=int(data["assignment_id"]),
            submitted_at=submitted_at,
            workflow_state=data.get("workflow_state", "unsubmitted"),
            score=data.get("score"),
            grade=data.get("grade"),
        )


@dataclass(frozen=True)
class Assignment:
    """
    Represents a Canvas assignment.
    
    The unique identity is (course_id, id).
    Never rely on name alone for identity.
    
    Attributes:
        id: Unique assignment ID within Canvas
        course_id: The course this assignment belongs to
        course_name: Name of the course (for display)
        name: Assignment name/title
        description: Assignment description (HTML)
        due_at: Due date/time, None if no due date
        html_url: URL to view assignment in Canvas
        points_possible: Maximum points for assignment
        submission: User's submission status, None if not fetched
        published: Whether assignment is published
    """
    id: int
    course_id: int
    course_name: str
    name: str
    description: Optional[str]
    due_at: Optional[datetime]
    html_url: str
    points_possible: Optional[float]
    submission: Optional[Submission] = None
    published: bool = True
    
    def __post_init__(self):
        if not isinstance(self.id, int) or self.id <= 0:
            raise ValueError(f"Assignment ID must be a positive integer, got {self.id}")
        if not isinstance(self.course_id, int) or self.course_id <= 0:
            raise ValueError(f"Course ID must be a positive integer, got {self.course_id}")
    
    @property
    def unique_key(self) -> tuple[int, int]:
        """Return the unique identifier for this assignment."""
        return (self.course_id, self.id)
    
    @property
    def display_title(self) -> str:
        """Return formatted title for Outlook task."""
        return f"[{self.course_name}] {self.name}"
    
    @property
    def is_submitted(self) -> bool:
        """Check if this assignment has been submitted."""
        if self.submission is None:
            return False
        return self.submission.is_submitted
    
    @classmethod
    def from_api_response(
        cls, 
        data: dict, 
        course_id: int, 
        course_name: str,
        submission: Optional[Submission] = None
    ) -> "Assignment":
        """Create Assignment from Canvas API response."""
        due_at = None
        if data.get("due_at"):
            due_at = datetime.fromisoformat(
                data["due_at"].replace("Z", "+00:00")
            )
        
        return cls(
            id=int(data["id"]),
            course_id=course_id,
            course_name=course_name,
            name=data.get("name", "Untitled Assignment"),
            description=data.get("description"),
            due_at=due_at,
            html_url=data.get("html_url", ""),
            points_possible=data.get("points_possible"),
            submission=submission,
            published=data.get("published", True),
        )
