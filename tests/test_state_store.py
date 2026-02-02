"""
Unit tests for SQLite state store.
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path

from src.storage.state_store import StateStore
from src.storage.models import SyncState


class TestStateStore:
    """Tests for StateStore operations."""

    def test_initialize_creates_database(self, temp_db_path: Path):
        """Test that StateStore creates database file."""
        store = StateStore(temp_db_path)
        assert temp_db_path.exists()

    def test_get_nonexistent_returns_none(self, state_store: StateStore):
        """Test getting non-existent state returns None."""
        result = state_store.get(course_id=99999, assignment_id=99999)
        assert result is None

    def test_save_and_get(self, state_store: StateStore, sample_sync_state: SyncState):
        """Test saving and retrieving state."""
        saved = state_store.save(sample_sync_state)
        
        retrieved = state_store.get(
            course_id=sample_sync_state.canvas_course_id,
            assignment_id=sample_sync_state.canvas_assignment_id,
        )
        
        assert retrieved is not None
        assert retrieved.canvas_course_id == sample_sync_state.canvas_course_id
        assert retrieved.canvas_assignment_id == sample_sync_state.canvas_assignment_id
        assert retrieved.outlook_task_id == sample_sync_state.outlook_task_id

    def test_save_updates_synced_at(self, state_store: StateStore, sample_sync_state: SyncState):
        """Test that save updates last_synced_at."""
        before = datetime.utcnow()
        saved = state_store.save(sample_sync_state)
        after = datetime.utcnow()
        
        assert saved.last_synced_at is not None
        # Allow 1 second tolerance
        assert before <= saved.last_synced_at <= after

    def test_get_by_outlook_task_id(self, state_store: StateStore, sample_sync_state: SyncState):
        """Test retrieving state by Outlook task ID."""
        state_store.save(sample_sync_state)
        
        retrieved = state_store.get_by_outlook_task_id(sample_sync_state.outlook_task_id)
        
        assert retrieved is not None
        assert retrieved.canvas_assignment_id == sample_sync_state.canvas_assignment_id

    def test_get_all_empty(self, state_store: StateStore):
        """Test get_all on empty database."""
        result = state_store.get_all()
        assert result == []

    def test_get_all_returns_all(self, state_store: StateStore):
        """Test get_all returns all non-archived states."""
        # Create multiple states
        for i in range(3):
            state = SyncState(
                canvas_course_id=100,
                canvas_assignment_id=200 + i,
                outlook_task_id=f"task-{i}",
                last_seen_submission_state="not_submitted",
            )
            state_store.save(state)
        
        result = state_store.get_all()
        assert len(result) == 3

    def test_archive_marks_as_archived(self, state_store: StateStore, sample_sync_state: SyncState):
        """Test archiving an assignment."""
        state_store.save(sample_sync_state)
        
        result = state_store.archive(
            course_id=sample_sync_state.canvas_course_id,
            assignment_id=sample_sync_state.canvas_assignment_id,
        )
        
        assert result is True
        
        # Should not appear in get_all without archived flag
        all_states = state_store.get_all(include_archived=False)
        assert len(all_states) == 0
        
        # Should appear with archived flag
        all_states = state_store.get_all(include_archived=True)
        assert len(all_states) == 1
        assert all_states[0].is_archived is True

    def test_archive_nonexistent_returns_false(self, state_store: StateStore):
        """Test archiving non-existent state returns False."""
        result = state_store.archive(course_id=99999, assignment_id=99999)
        assert result is False

    def test_get_synced_assignment_keys(self, state_store: StateStore):
        """Test getting synced assignment keys."""
        # Save some states
        for i in range(3):
            state = SyncState(
                canvas_course_id=100,
                canvas_assignment_id=200 + i,
                outlook_task_id=f"task-{i}",
                last_seen_submission_state="not_submitted",
            )
            state_store.save(state)
        
        keys = state_store.get_synced_assignment_keys()
        
        assert len(keys) == 3
        assert (100, 200) in keys
        assert (100, 201) in keys
        assert (100, 202) in keys

    def test_count(self, state_store: StateStore, sample_sync_state: SyncState):
        """Test counting records."""
        assert state_store.count() == 0
        
        state_store.save(sample_sync_state)
        assert state_store.count() == 1

    def test_count_excludes_archived(self, state_store: StateStore, sample_sync_state: SyncState):
        """Test count excludes archived by default."""
        state_store.save(sample_sync_state)
        state_store.archive(
            course_id=sample_sync_state.canvas_course_id,
            assignment_id=sample_sync_state.canvas_assignment_id,
        )
        
        assert state_store.count(include_archived=False) == 0
        assert state_store.count(include_archived=True) == 1

    def test_clear(self, state_store: StateStore, sample_sync_state: SyncState):
        """Test clearing all state."""
        state_store.save(sample_sync_state)
        assert state_store.count() == 1
        
        state_store.clear()
        assert state_store.count() == 0

    def test_upsert_updates_existing(self, state_store: StateStore):
        """Test that save updates existing records."""
        state = SyncState(
            canvas_course_id=100,
            canvas_assignment_id=200,
            outlook_task_id="task-1",
            last_seen_submission_state="not_submitted",
        )
        state_store.save(state)
        
        # Update the state
        updated_state = SyncState(
            canvas_course_id=100,
            canvas_assignment_id=200,
            outlook_task_id="task-1",
            last_seen_submission_state="submitted",  # Changed
        )
        state_store.save(updated_state)
        
        # Should still be only 1 record
        assert state_store.count() == 1
        
        # Should have updated value
        retrieved = state_store.get(course_id=100, assignment_id=200)
        assert retrieved.last_seen_submission_state == "submitted"
