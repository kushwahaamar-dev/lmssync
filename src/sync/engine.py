"""
Diff-based sync engine.

Orchestrates the synchronization between Canvas and Outlook.
Implements idempotent operations with explicit error handling.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from ..canvas.client import CanvasClient, CanvasAPIError
from ..canvas.models import Assignment
from ..outlook.client import OutlookClient, GraphAPIError
from ..outlook.models import OutlookTask, TaskStatus, CanvasTaskMetadata
from ..storage.state_store import StateStore
from ..storage.models import SyncState
from .diff import DiffResult, ChangeType, compute_diff, compute_deleted_assignments

logger = logging.getLogger(__name__)


@dataclass
class SyncStats:
    """Statistics from a sync run."""
    total_assignments: int = 0
    created: int = 0
    updated: int = 0
    completed: int = 0
    reopened: int = 0
    archived: int = 0
    skipped: int = 0
    errors: int = 0
    
    def __str__(self) -> str:
        return (
            f"Sync complete: {self.total_assignments} assignments, "
            f"{self.created} created, {self.updated} updated, "
            f"{self.completed} completed, {self.reopened} reopened, "
            f"{self.archived} archived, {self.skipped} skipped, "
            f"{self.errors} errors"
        )


@dataclass
class SyncError:
    """Represents an error during sync."""
    assignment_key: tuple[int, int]
    error_type: str
    message: str
    recoverable: bool = True


class SyncEngine:
    """
    Orchestrates synchronization between Canvas and Outlook.
    
    Core principles:
    - Every operation is idempotent
    - Re-running never corrupts state
    - Partial failures don't block other assignments
    - State is persisted atomically after each operation
    
    Usage:
        engine = SyncEngine(
            canvas_client=canvas_client,
            outlook_client=outlook_client,
            state_store=state_store,
            task_list_name="Canvas Assignments",
        )
        
        stats = engine.sync()
        print(stats)
    """
    
    def __init__(
        self,
        canvas_client: CanvasClient,
        outlook_client: OutlookClient,
        state_store: StateStore,
        task_list_name: str = "Canvas Assignments",
        dry_run: bool = False,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        """
        Initialize sync engine.
        
        Args:
            canvas_client: Configured Canvas API client
            outlook_client: Configured Outlook API client
            state_store: Persistent state store
            task_list_name: Name of Outlook task list to sync to
            dry_run: If True, don't make any changes
            max_retries: Maximum retries for transient failures
            retry_delay: Delay between retries in seconds
        """
        self.canvas = canvas_client
        self.outlook = outlook_client
        self.state_store = state_store
        self.task_list_name = task_list_name
        self.dry_run = dry_run
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        self._task_list_id: Optional[str] = None
        self._errors: list[SyncError] = []
    
    def sync(self) -> SyncStats:
        """
        Execute full synchronization.
        
        Steps:
        1. Fetch all active assignments from Canvas
        2. Get or create Outlook task list
        3. For each assignment, compute diff and apply changes
        4. Detect deleted assignments and archive them
        
        Returns:
            SyncStats with counts of all operations
        """
        stats = SyncStats()
        self._errors = []
        
        if self.dry_run:
            logger.info("DRY RUN MODE - No changes will be made")
        
        logger.info("Starting sync...")
        
        # Step 1: Fetch all assignments from Canvas
        try:
            assignments = self.canvas.get_all_assignments()
            stats.total_assignments = len(assignments)
            logger.info(f"Fetched {len(assignments)} assignments from Canvas")
        except CanvasAPIError as e:
            logger.error(f"Failed to fetch Canvas assignments: {e}")
            raise
        
        # Step 2: Get or create Outlook task list
        try:
            task_list = self.outlook.get_or_create_task_list(self.task_list_name)
            self._task_list_id = task_list.id
            logger.info(f"Using task list: {task_list.display_name} ({task_list.id})")
        except GraphAPIError as e:
            logger.error(f"Failed to get/create task list: {e}")
            raise
        
        # Step 3: Process each assignment
        current_keys = set()
        
        for assignment in assignments:
            current_keys.add(assignment.unique_key)
            
            try:
                result = self._process_assignment(assignment)
                self._update_stats(stats, result)
            except Exception as e:
                logger.error(
                    f"Error processing assignment {assignment.unique_key}: {e}",
                    exc_info=True,
                )
                stats.errors += 1
                self._errors.append(SyncError(
                    assignment_key=assignment.unique_key,
                    error_type=type(e).__name__,
                    message=str(e),
                ))
        
        # Step 4: Archive deleted assignments
        try:
            archived_count = self._archive_deleted_assignments(current_keys)
            stats.archived = archived_count
        except Exception as e:
            logger.error(f"Error archiving deleted assignments: {e}", exc_info=True)
            stats.errors += 1
        
        logger.info(str(stats))
        
        if self._errors:
            logger.warning(f"Sync completed with {len(self._errors)} errors")
            for error in self._errors:
                logger.warning(f"  - {error.assignment_key}: {error.message}")
        
        return stats
    
    def _process_assignment(self, assignment: Assignment) -> DiffResult:
        """
        Process a single assignment.
        
        Computes diff and applies necessary changes.
        
        Args:
            assignment: Canvas assignment to process
            
        Returns:
            DiffResult describing what was done
        """
        logger.debug(f"Processing assignment: {assignment.display_title}")
        
        # Get current state
        state = self.state_store.get(
            assignment.course_id,
            assignment.id,
        )
        
        # Compute diff
        diff = compute_diff(assignment, state)
        
        if not diff.needs_update:
            logger.debug(f"No changes for {assignment.display_title}")
            return diff
        
        logger.info(
            f"Changes detected for {assignment.display_title}: "
            f"{[c.name for c in diff.changes]}"
        )
        
        if self.dry_run:
            logger.info(f"DRY RUN: Would apply changes: {diff.changes}")
            return diff
        
        # Apply changes
        if diff.is_new:
            self._create_task(assignment, diff)
        else:
            self._update_task(assignment, diff, state)
        
        return diff
    
    def _create_task(self, assignment: Assignment, diff: DiffResult) -> None:
        """
        Create a new Outlook task for an assignment.
        
        Args:
            assignment: Canvas assignment
            diff: Computed diff result
        """
        logger.info(f"Creating task for: {assignment.display_title}")
        
        # Build task
        metadata = CanvasTaskMetadata(
            canvas_course_id=assignment.course_id,
            canvas_assignment_id=assignment.id,
            canvas_url=assignment.html_url,
        )
        
        task = OutlookTask(
            title=assignment.display_title,
            body_content=metadata.to_body_content(),
            due_date=assignment.due_at.date() if assignment.due_at else None,
            status=TaskStatus.COMPLETED if assignment.is_submitted else TaskStatus.NOT_STARTED,
        )
        
        # Create with retry
        created_task = self._retry_operation(
            lambda: self.outlook.create_task(self._task_list_id, task),
            f"create task {assignment.display_title}",
        )
        
        # Save state
        new_state = SyncState(
            canvas_course_id=assignment.course_id,
            canvas_assignment_id=assignment.id,
            outlook_task_id=created_task.id,
            last_seen_submission_state="submitted" if assignment.is_submitted else "not_submitted",
            last_seen_due_date=assignment.due_at.date().isoformat() if assignment.due_at else None,
            last_seen_title=assignment.display_title,
        )
        
        self.state_store.save(new_state)
        logger.info(f"Created task: {created_task.id}")
    
    def _update_task(
        self,
        assignment: Assignment,
        diff: DiffResult,
        state: SyncState,
    ) -> None:
        """
        Update an existing Outlook task.
        
        Only updates fields that have changed (minimal update).
        
        Args:
            assignment: Canvas assignment
            diff: Computed diff result
            state: Current sync state
        """
        updates = {}
        
        # Build minimal update payload
        if ChangeType.SUBMITTED in diff.changes:
            logger.info(f"Marking completed: {assignment.display_title}")
            updates["status"] = TaskStatus.COMPLETED
        elif ChangeType.UNSUBMITTED in diff.changes:
            logger.info(f"Reopening: {assignment.display_title}")
            updates["status"] = TaskStatus.NOT_STARTED
        
        if ChangeType.DUE_DATE_CHANGED in diff.changes:
            logger.info(f"Updating due date: {diff.new_due_date}")
            updates["due_date"] = diff.new_due_date
        
        if ChangeType.TITLE_CHANGED in diff.changes:
            logger.info(f"Updating title: {diff.new_title}")
            updates["title"] = diff.new_title
        
        if not updates:
            return
        
        # Apply update with retry
        self._retry_operation(
            lambda: self.outlook.update_task(
                self._task_list_id,
                state.outlook_task_id,
                updates,
            ),
            f"update task {assignment.display_title}",
        )
        
        # Update state
        new_state = SyncState(
            canvas_course_id=assignment.course_id,
            canvas_assignment_id=assignment.id,
            outlook_task_id=state.outlook_task_id,
            last_seen_submission_state=diff.new_submission_state or state.last_seen_submission_state,
            last_seen_due_date=(
                diff.new_due_date.isoformat() if diff.new_due_date 
                else state.last_seen_due_date
            ),
            last_seen_title=diff.new_title or state.last_seen_title,
            created_at=state.created_at,
        )
        
        self.state_store.save(new_state)
        logger.debug(f"Updated state for {assignment.unique_key}")
    
    def _archive_deleted_assignments(
        self,
        current_keys: set[tuple[int, int]],
    ) -> int:
        """
        Archive assignments that no longer exist in Canvas.
        
        Does NOT delete Outlook tasks, only marks them as archived
        in the local state store.
        
        Args:
            current_keys: Set of (course_id, assignment_id) from Canvas
            
        Returns:
            Number of assignments archived
        """
        synced_keys = self.state_store.get_synced_assignment_keys()
        deleted_keys = compute_deleted_assignments(current_keys, synced_keys)
        
        if not deleted_keys:
            return 0
        
        logger.info(f"Found {len(deleted_keys)} deleted assignments to archive")
        
        archived = 0
        for course_id, assignment_id in deleted_keys:
            if self.dry_run:
                logger.info(f"DRY RUN: Would archive ({course_id}, {assignment_id})")
                continue
            
            if self.state_store.archive(course_id, assignment_id):
                archived += 1
                logger.info(f"Archived assignment ({course_id}, {assignment_id})")
        
        return archived
    
    def _update_stats(self, stats: SyncStats, diff: DiffResult) -> None:
        """Update stats based on diff result."""
        if ChangeType.NO_CHANGE in diff.changes:
            stats.skipped += 1
        elif ChangeType.NEW_ASSIGNMENT in diff.changes:
            stats.created += 1
            if ChangeType.SUBMITTED in diff.changes:
                stats.completed += 1
        else:
            if ChangeType.SUBMITTED in diff.changes:
                stats.completed += 1
            if ChangeType.UNSUBMITTED in diff.changes:
                stats.reopened += 1
            if (ChangeType.DUE_DATE_CHANGED in diff.changes or 
                ChangeType.TITLE_CHANGED in diff.changes):
                stats.updated += 1
    
    def _retry_operation(self, operation, description: str):
        """
        Execute an operation with retry logic.
        
        Args:
            operation: Callable to execute
            description: Human-readable description for logging
            
        Returns:
            Result of operation
            
        Raises:
            Last exception if all retries failed
        """
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                return operation()
            except (GraphAPIError, CanvasAPIError) as e:
                last_error = e
                
                # Don't retry on auth errors
                if hasattr(e, "status_code") and e.status_code in (401, 403):
                    raise
                
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        f"Retry {attempt + 1}/{self.max_retries} for {description}: {e}. "
                        f"Waiting {delay}s..."
                    )
                    time.sleep(delay)
        
        logger.error(f"All retries failed for {description}: {last_error}")
        raise last_error
    
    @property
    def errors(self) -> list[SyncError]:
        """Get list of errors from last sync."""
        return self._errors.copy()
