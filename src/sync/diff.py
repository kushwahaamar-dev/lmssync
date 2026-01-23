"""
Diff detection for sync engine.

Compares Canvas assignments against stored state to determine
what actions need to be taken.
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum, auto
from typing import Optional

from ..canvas.models import Assignment
from ..storage.models import SyncState


class ChangeType(Enum):
    """Types of changes detected between Canvas and stored state."""
    
    # Task does not exist - needs to be created
    NEW_ASSIGNMENT = auto()
    
    # Assignment was submitted - mark task completed
    SUBMITTED = auto()
    
    # Assignment was unsubmitted - reopen task
    UNSUBMITTED = auto()
    
    # Due date changed - update task
    DUE_DATE_CHANGED = auto()
    
    # Assignment renamed - update task title
    TITLE_CHANGED = auto()
    
    # Assignment no longer exists - archive
    DELETED = auto()
    
    # No changes detected
    NO_CHANGE = auto()


@dataclass
class DiffResult:
    """
    Result of comparing a Canvas assignment against stored state.
    
    Attributes:
        assignment: The Canvas assignment being compared
        state: Existing sync state (None for new assignments)
        changes: List of detected change types
        new_title: New title if changed
        new_due_date: New due date if changed
        new_submission_state: New submission state if changed
    """
    assignment: Assignment
    state: Optional[SyncState]
    changes: list[ChangeType] = field(default_factory=list)
    new_title: Optional[str] = None
    new_due_date: Optional[date] = None
    new_submission_state: Optional[str] = None
    
    @property
    def is_new(self) -> bool:
        """Check if this is a new assignment."""
        return ChangeType.NEW_ASSIGNMENT in self.changes
    
    @property
    def needs_update(self) -> bool:
        """Check if any update is needed."""
        return len(self.changes) > 0 and ChangeType.NO_CHANGE not in self.changes
    
    @property
    def needs_completion_change(self) -> bool:
        """Check if completion status changed."""
        return (
            ChangeType.SUBMITTED in self.changes or
            ChangeType.UNSUBMITTED in self.changes
        )
    
    def __repr__(self) -> str:
        change_names = [c.name for c in self.changes]
        return (
            f"DiffResult(assignment={self.assignment.unique_key}, "
            f"changes={change_names})"
        )


def compute_diff(
    assignment: Assignment,
    state: Optional[SyncState],
) -> DiffResult:
    """
    Compute the diff between a Canvas assignment and stored state.
    
    This is the core logic that determines what actions need to be taken.
    
    Rules:
    - New assignment (no state) → NEW_ASSIGNMENT
    - submitted_at changed from None to value → SUBMITTED
    - submitted_at changed from value to None → UNSUBMITTED
    - due_at changed → DUE_DATE_CHANGED
    - name changed → TITLE_CHANGED
    
    Args:
        assignment: Current Canvas assignment data
        state: Stored sync state (None if never synced)
        
    Returns:
        DiffResult with all detected changes
    """
    result = DiffResult(assignment=assignment, state=state)
    
    # Case 1: New assignment
    if state is None or state.outlook_task_id is None:
        result.changes.append(ChangeType.NEW_ASSIGNMENT)
        result.new_title = assignment.display_title
        result.new_submission_state = "submitted" if assignment.is_submitted else "not_submitted"
        
        if assignment.due_at:
            result.new_due_date = assignment.due_at.date()
        
        return result
    
    # Track all changes
    changes_detected = False
    
    # Case 2: Submission state changed
    current_submitted = assignment.is_submitted
    was_submitted = state.was_submitted
    
    if current_submitted and not was_submitted:
        result.changes.append(ChangeType.SUBMITTED)
        result.new_submission_state = "submitted"
        changes_detected = True
    elif not current_submitted and was_submitted:
        result.changes.append(ChangeType.UNSUBMITTED)
        result.new_submission_state = "not_submitted"
        changes_detected = True
    
    # Case 3: Due date changed
    current_due = assignment.due_at.date() if assignment.due_at else None
    stored_due = state.due_date_as_date
    
    if current_due != stored_due:
        result.changes.append(ChangeType.DUE_DATE_CHANGED)
        result.new_due_date = current_due
        changes_detected = True
    
    # Case 4: Title changed
    current_title = assignment.display_title
    stored_title = state.last_seen_title
    
    if current_title != stored_title:
        result.changes.append(ChangeType.TITLE_CHANGED)
        result.new_title = current_title
        changes_detected = True
    
    # Case 5: No changes
    if not changes_detected:
        result.changes.append(ChangeType.NO_CHANGE)
    
    return result


def compute_deleted_assignments(
    current_assignment_keys: set[tuple[int, int]],
    synced_assignment_keys: set[tuple[int, int]],
) -> set[tuple[int, int]]:
    """
    Find assignments that were synced but no longer exist in Canvas.
    
    These assignments should be archived (NOT deleted).
    
    Args:
        current_assignment_keys: (course_id, assignment_id) pairs from Canvas
        synced_assignment_keys: (course_id, assignment_id) pairs from state store
        
    Returns:
        Set of (course_id, assignment_id) tuples for deleted assignments
    """
    return synced_assignment_keys - current_assignment_keys
