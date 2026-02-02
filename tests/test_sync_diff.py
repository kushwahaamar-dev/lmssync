"""
Unit tests for diff computation logic.
"""

import pytest
from datetime import datetime, timezone, date

from src.canvas.models import Assignment, Course, Submission
from src.sync.diff import DiffResult, ChangeType, compute_diff
from src.storage.models import SyncState


class TestChangeType:
    """Tests for ChangeType enum."""

    def test_no_change_is_falsy(self):
        """Test NO_CHANGE evaluates appropriately."""
        assert ChangeType.NO_CHANGE.value == "no_change"

    def test_create_exists(self):
        """Test CREATE change type."""
        assert ChangeType.CREATE.value == "create"


class TestDiffResult:
    """Tests for DiffResult dataclass."""

    def test_requires_action_for_create(self):
        """Test that CREATE requires action."""
        diff = DiffResult(change_type=ChangeType.CREATE)
        assert diff.requires_action is True

    def test_no_action_for_no_change(self):
        """Test that NO_CHANGE doesn't require action."""
        diff = DiffResult(change_type=ChangeType.NO_CHANGE)
        assert diff.requires_action is False


class TestComputeDiff:
    """Tests for compute_diff function."""

    @pytest.fixture
    def base_assignment(self) -> Assignment:
        """Create base assignment for testing."""
        return Assignment(
            id=67890,
            course_id=12345,
            course_name="CS101",
            name="Test Assignment",
            description=None,
            due_at=datetime(2026, 1, 20, 23, 59, 0, tzinfo=timezone.utc),
            html_url="https://canvas.example.com/assignments/67890",
            points_possible=100.0,
            submission=Submission(
                assignment_id=67890,
                submitted_at=None,
                workflow_state="unsubmitted",
            ),
            published=True,
        )

    def test_new_assignment_returns_create(self, base_assignment: Assignment):
        """Test that new assignment returns CREATE diff."""
        diff = compute_diff(assignment=base_assignment, stored_state=None)
        
        assert diff.change_type == ChangeType.CREATE
        assert diff.requires_action is True

    def test_no_change_when_identical(self, base_assignment: Assignment):
        """Test NO_CHANGE when assignment matches stored state."""
        stored = SyncState(
            canvas_course_id=12345,
            canvas_assignment_id=67890,
            outlook_task_id="task-123",
            last_seen_submission_state="not_submitted",
            last_seen_due_date="2026-01-20",
            last_seen_title="[CS101] Test Assignment",
        )
        
        diff = compute_diff(assignment=base_assignment, stored_state=stored)
        
        assert diff.change_type == ChangeType.NO_CHANGE
        assert diff.requires_action is False

    def test_submission_change_detected(self, base_assignment: Assignment):
        """Test submission state change detection."""
        # Create assignment with submission
        submitted_assignment = Assignment(
            id=67890,
            course_id=12345,
            course_name="CS101",
            name="Test Assignment",
            description=None,
            due_at=datetime(2026, 1, 20, 23, 59, 0, tzinfo=timezone.utc),
            html_url="https://canvas.example.com/assignments/67890",
            points_possible=100.0,
            submission=Submission(
                assignment_id=67890,
                submitted_at=datetime(2026, 1, 18, 10, 0, 0, tzinfo=timezone.utc),
                workflow_state="submitted",
            ),
            published=True,
        )
        
        stored = SyncState(
            canvas_course_id=12345,
            canvas_assignment_id=67890,
            outlook_task_id="task-123",
            last_seen_submission_state="not_submitted",
            last_seen_due_date="2026-01-20",
            last_seen_title="[CS101] Test Assignment",
        )
        
        diff = compute_diff(assignment=submitted_assignment, stored_state=stored)
        
        assert diff.change_type == ChangeType.COMPLETE
        assert diff.requires_action is True
        assert diff.submission_changed is True

    def test_due_date_change_detected(self, base_assignment: Assignment):
        """Test due date change detection."""
        stored = SyncState(
            canvas_course_id=12345,
            canvas_assignment_id=67890,
            outlook_task_id="task-123",
            last_seen_submission_state="not_submitted",
            last_seen_due_date="2026-01-15",  # Different date
            last_seen_title="[CS101] Test Assignment",
        )
        
        diff = compute_diff(assignment=base_assignment, stored_state=stored)
        
        assert diff.change_type == ChangeType.UPDATE
        assert diff.due_date_changed is True

    def test_title_change_detected(self, base_assignment: Assignment):
        """Test title change detection."""
        stored = SyncState(
            canvas_course_id=12345,
            canvas_assignment_id=67890,
            outlook_task_id="task-123",
            last_seen_submission_state="not_submitted",
            last_seen_due_date="2026-01-20",
            last_seen_title="[CS101] Old Title",  # Different title
        )
        
        diff = compute_diff(assignment=base_assignment, stored_state=stored)
        
        assert diff.change_type == ChangeType.UPDATE
        assert diff.title_changed is True

    def test_reopen_when_unsubmitted_again(self):
        """Test REOPEN when submission removed."""
        # Assignment with no submission (was previously submitted)
        assignment = Assignment(
            id=67890,
            course_id=12345,
            course_name="CS101",
            name="Test Assignment",
            description=None,
            due_at=None,
            html_url="",
            points_possible=None,
            submission=Submission(
                assignment_id=67890,
                submitted_at=None,
                workflow_state="unsubmitted",
            ),
        )
        
        stored = SyncState(
            canvas_course_id=12345,
            canvas_assignment_id=67890,
            outlook_task_id="task-123",
            last_seen_submission_state="submitted",  # Was submitted
            last_seen_due_date=None,
            last_seen_title="[CS101] Test Assignment",
        )
        
        diff = compute_diff(assignment=assignment, stored_state=stored)
        
        assert diff.change_type == ChangeType.REOPEN
        assert diff.requires_action is True
