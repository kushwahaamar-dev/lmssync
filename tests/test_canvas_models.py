"""
Unit tests for Canvas data models.
"""

import pytest
from datetime import datetime, timezone

from src.canvas.models import Assignment, Course, Submission


class TestCourse:
    """Tests for Course model."""

    def test_create_course(self, sample_course: Course):
        """Test creating a course with valid data."""
        assert sample_course.id == 12345
        assert sample_course.name == "Introduction to Computer Science"
        assert sample_course.code == "CS101"
        assert sample_course.enrollment_state == "active"

    def test_course_from_api_response(self, canvas_course_response: dict):
        """Test creating course from API response."""
        course = Course.from_api_response(canvas_course_response)
        assert course.id == 12345
        assert course.name == "Introduction to Computer Science"
        assert course.code == "CS101"

    def test_course_invalid_id(self):
        """Test that invalid course ID raises error."""
        with pytest.raises(ValueError, match="positive integer"):
            Course(id=-1, name="Test", code="TST", enrollment_state="active")

    def test_course_zero_id(self):
        """Test that zero course ID raises error."""
        with pytest.raises(ValueError, match="positive integer"):
            Course(id=0, name="Test", code="TST", enrollment_state="active")


class TestSubmission:
    """Tests for Submission model."""

    def test_submitted_submission(self, sample_submission: Submission):
        """Test submission with submitted_at date."""
        assert sample_submission.is_submitted is True
        assert sample_submission.submitted_at is not None
        assert sample_submission.workflow_state == "submitted"

    def test_unsubmitted_submission(self, sample_unsubmitted: Submission):
        """Test unsubmitted submission."""
        assert sample_unsubmitted.is_submitted is False
        assert sample_unsubmitted.submitted_at is None

    def test_graded_is_submitted(self):
        """Test that graded workflow state counts as submitted."""
        sub = Submission(
            assignment_id=1,
            submitted_at=None,
            workflow_state="graded",
        )
        assert sub.is_submitted is True

    def test_pending_review_is_submitted(self):
        """Test that pending_review counts as submitted."""
        sub = Submission(
            assignment_id=1,
            submitted_at=None,
            workflow_state="pending_review",
        )
        assert sub.is_submitted is True

    def test_from_api_response(self, canvas_submission_response: dict):
        """Test creating submission from API response."""
        sub = Submission.from_api_response(canvas_submission_response)
        assert sub.assignment_id == 67890
        assert sub.is_submitted is True
        assert sub.score == 95.0
        assert sub.grade == "A"


class TestAssignment:
    """Tests for Assignment model."""

    def test_assignment_properties(self, sample_assignment: Assignment):
        """Test assignment basic properties."""
        assert sample_assignment.id == 67890
        assert sample_assignment.course_id == 12345
        assert sample_assignment.name == "Homework 1: Python Basics"
        assert sample_assignment.published is True

    def test_unique_key(self, sample_assignment: Assignment):
        """Test assignment unique key."""
        assert sample_assignment.unique_key == (12345, 67890)

    def test_display_title(self, sample_assignment: Assignment):
        """Test display title formatting."""
        expected = "[Introduction to Computer Science] Homework 1: Python Basics"
        assert sample_assignment.display_title == expected

    def test_is_submitted_true(self, sample_assignment: Assignment):
        """Test is_submitted with submitted assignment."""
        assert sample_assignment.is_submitted is True

    def test_is_submitted_no_submission(self, sample_assignment_no_due_date: Assignment):
        """Test is_submitted with no submission data."""
        assert sample_assignment_no_due_date.is_submitted is False

    def test_assignment_invalid_id(self, sample_course: Course):
        """Test that invalid assignment ID raises error."""
        with pytest.raises(ValueError, match="Assignment ID must be"):
            Assignment(
                id=0,
                course_id=sample_course.id,
                course_name=sample_course.name,
                name="Test",
                description=None,
                due_at=None,
                html_url="",
                points_possible=None,
            )

    def test_from_api_response(
        self,
        canvas_assignment_response: dict,
        sample_submission: Submission,
    ):
        """Test creating assignment from API response."""
        assignment = Assignment.from_api_response(
            data=canvas_assignment_response,
            course_id=12345,
            course_name="CS101",
            submission=sample_submission,
        )
        assert assignment.id == 67890
        assert assignment.name == "Homework 1: Python Basics"
        assert assignment.due_at is not None
        assert assignment.is_submitted is True
