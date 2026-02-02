"""
Pytest configuration and shared fixtures.

Provides mocks and test data for Canvas/Outlook API testing.
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator
import tempfile

from src.canvas.models import Assignment, Course, Submission
from src.outlook.models import OutlookTask, TaskList, TaskStatus
from src.storage.state_store import StateStore
from src.storage.models import SyncState


# ============================================================================
# Canvas Model Fixtures
# ============================================================================

@pytest.fixture
def sample_course() -> Course:
    """Create a sample Canvas course."""
    return Course(
        id=12345,
        name="Introduction to Computer Science",
        code="CS101",
        enrollment_state="active",
    )


@pytest.fixture
def sample_submission() -> Submission:
    """Create a sample submitted submission."""
    return Submission(
        assignment_id=67890,
        submitted_at=datetime(2026, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
        workflow_state="submitted",
        score=95.0,
        grade="A",
    )


@pytest.fixture
def sample_unsubmitted() -> Submission:
    """Create an unsubmitted submission."""
    return Submission(
        assignment_id=67891,
        submitted_at=None,
        workflow_state="unsubmitted",
    )


@pytest.fixture
def sample_assignment(sample_course: Course, sample_submission: Submission) -> Assignment:
    """Create a sample assignment with submission."""
    return Assignment(
        id=67890,
        course_id=sample_course.id,
        course_name=sample_course.name,
        name="Homework 1: Python Basics",
        description="<p>Complete the exercises.</p>",
        due_at=datetime(2026, 1, 20, 23, 59, 0, tzinfo=timezone.utc),
        html_url="https://canvas.example.com/courses/12345/assignments/67890",
        points_possible=100.0,
        submission=sample_submission,
        published=True,
    )


@pytest.fixture
def sample_assignment_no_due_date(sample_course: Course) -> Assignment:
    """Create an assignment without a due date."""
    return Assignment(
        id=67892,
        course_id=sample_course.id,
        course_name=sample_course.name,
        name="Optional Extra Credit",
        description=None,
        due_at=None,
        html_url="https://canvas.example.com/courses/12345/assignments/67892",
        points_possible=None,
    )


# ============================================================================
# Outlook Model Fixtures
# ============================================================================

@pytest.fixture
def sample_task_list() -> TaskList:
    """Create a sample Outlook task list."""
    return TaskList(
        id="AAMkAG...",
        display_name="Canvas Assignments",
        is_owner=True,
    )


@pytest.fixture
def sample_outlook_task() -> OutlookTask:
    """Create a sample Outlook task."""
    return OutlookTask(
        id="AAMkAGTask...",
        title="[CS101] Homework 1: Python Basics",
        body="Canvas URL: https://canvas.example.com/courses/12345/assignments/67890",
        due_date=datetime(2026, 1, 20).date(),
        status=TaskStatus.NOT_STARTED,
    )


# ============================================================================
# Storage Fixtures
# ============================================================================

@pytest.fixture
def temp_db_path() -> Generator[Path, None, None]:
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    yield path
    # Cleanup
    if path.exists():
        path.unlink()


@pytest.fixture
def state_store(temp_db_path: Path) -> StateStore:
    """Create a fresh StateStore with temp database."""
    return StateStore(temp_db_path)


@pytest.fixture
def sample_sync_state() -> SyncState:
    """Create a sample sync state."""
    return SyncState(
        canvas_course_id=12345,
        canvas_assignment_id=67890,
        outlook_task_id="AAMkAGTask...",
        last_seen_submission_state="submitted",
        last_seen_due_date="2026-01-20",
        last_seen_title="[CS101] Homework 1: Python Basics",
        last_synced_at=datetime(2026, 1, 15, 10, 0, 0),
        is_archived=False,
        created_at=datetime(2026, 1, 10, 8, 0, 0),
    )


# ============================================================================
# API Response Fixtures
# ============================================================================

@pytest.fixture
def canvas_course_response() -> dict:
    """Sample Canvas API course response."""
    return {
        "id": 12345,
        "name": "Introduction to Computer Science",
        "course_code": "CS101",
        "enrollment_state": "active",
    }


@pytest.fixture
def canvas_assignment_response() -> dict:
    """Sample Canvas API assignment response."""
    return {
        "id": 67890,
        "name": "Homework 1: Python Basics",
        "description": "<p>Complete the exercises.</p>",
        "due_at": "2026-01-20T23:59:00Z",
        "html_url": "https://canvas.example.com/courses/12345/assignments/67890",
        "points_possible": 100.0,
        "published": True,
    }


@pytest.fixture
def canvas_submission_response() -> dict:
    """Sample Canvas API submission response."""
    return {
        "assignment_id": 67890,
        "submitted_at": "2026-01-15T14:30:00Z",
        "workflow_state": "submitted",
        "score": 95.0,
        "grade": "A",
    }
