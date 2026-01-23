"""
SQLite-based persistent state store.

Provides atomic, durable storage for sync state.
All operations are idempotent and safe for concurrent access.
"""

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from .models import SyncState

logger = logging.getLogger(__name__)


class StateStoreError(Exception):
    """Raised when state store operations fail."""
    pass


class StateStore:
    """
    SQLite-based persistent state store.
    
    Features:
    - Atomic updates with transactions
    - Connection pooling via context manager
    - Automatic schema migration
    - Safe for scheduler-based usage
    
    Usage:
        store = StateStore(Path("data/sync_state.db"))
        
        # Get state for an assignment
        state = store.get(course_id=123, assignment_id=456)
        
        # Update state
        state.outlook_task_id = "abc..."
        store.save(state)
    """
    
    SCHEMA_VERSION = 1
    
    CREATE_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS sync_state (
            canvas_course_id INTEGER NOT NULL,
            canvas_assignment_id INTEGER NOT NULL,
            outlook_task_id TEXT,
            last_seen_submission_state TEXT DEFAULT 'not_submitted',
            last_seen_due_date TEXT,
            last_seen_title TEXT,
            last_synced_at TEXT,
            is_archived INTEGER DEFAULT 0,
            created_at TEXT,
            PRIMARY KEY (canvas_course_id, canvas_assignment_id)
        )
    """
    
    CREATE_INDEXES_SQL = [
        "CREATE INDEX IF NOT EXISTS idx_outlook_task_id ON sync_state(outlook_task_id)",
        "CREATE INDEX IF NOT EXISTS idx_is_archived ON sync_state(is_archived)",
    ]
    
    CREATE_METADATA_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS _metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """
    
    def __init__(self, database_path: Path):
        """
        Initialize state store.
        
        Args:
            database_path: Path to SQLite database file
        """
        self.database_path = database_path
        
        # Ensure parent directory exists
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self._initialize_database()
        
        logger.info(f"State store initialized at {self.database_path}")
    
    def _initialize_database(self) -> None:
        """Create tables and run migrations."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Create metadata table
            cursor.execute(self.CREATE_METADATA_TABLE_SQL)
            
            # Check schema version
            cursor.execute("SELECT value FROM _metadata WHERE key = 'schema_version'")
            row = cursor.fetchone()
            current_version = int(row[0]) if row else 0
            
            if current_version < self.SCHEMA_VERSION:
                logger.info(f"Upgrading schema from v{current_version} to v{self.SCHEMA_VERSION}")
                self._run_migrations(cursor, current_version)
                
                cursor.execute(
                    "INSERT OR REPLACE INTO _metadata (key, value) VALUES (?, ?)",
                    ("schema_version", str(self.SCHEMA_VERSION)),
                )
            
            # Create main table and indexes
            cursor.execute(self.CREATE_TABLE_SQL)
            for index_sql in self.CREATE_INDEXES_SQL:
                cursor.execute(index_sql)
            
            conn.commit()
    
    def _run_migrations(self, cursor: sqlite3.Cursor, from_version: int) -> None:
        """
        Run database migrations.
        
        Args:
            cursor: Database cursor
            from_version: Current schema version
        """
        # Future migrations go here
        # if from_version < 2:
        #     cursor.execute("ALTER TABLE sync_state ADD COLUMN new_column TEXT")
        pass
    
    @contextmanager
    def _get_connection(self) -> Iterator[sqlite3.Connection]:
        """
        Get a database connection with proper settings.
        
        Yields:
            SQLite connection with WAL mode and foreign keys enabled
        """
        conn = sqlite3.connect(
            self.database_path,
            timeout=30.0,
            isolation_level="DEFERRED",
        )
        
        try:
            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
        finally:
            conn.close()
    
    def get(self, course_id: int, assignment_id: int) -> Optional[SyncState]:
        """
        Get sync state for an assignment.
        
        Args:
            course_id: Canvas course ID
            assignment_id: Canvas assignment ID
            
        Returns:
            SyncState if found, None otherwise
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 
                    canvas_course_id,
                    canvas_assignment_id,
                    outlook_task_id,
                    last_seen_submission_state,
                    last_seen_due_date,
                    last_seen_title,
                    last_synced_at,
                    is_archived,
                    created_at
                FROM sync_state
                WHERE canvas_course_id = ? AND canvas_assignment_id = ?
                """,
                (course_id, assignment_id),
            )
            
            row = cursor.fetchone()
            if row:
                return SyncState.from_row(row)
            return None
    
    def get_by_outlook_task_id(self, task_id: str) -> Optional[SyncState]:
        """
        Get sync state by Outlook task ID.
        
        Args:
            task_id: Microsoft Graph task ID
            
        Returns:
            SyncState if found, None otherwise
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 
                    canvas_course_id,
                    canvas_assignment_id,
                    outlook_task_id,
                    last_seen_submission_state,
                    last_seen_due_date,
                    last_seen_title,
                    last_synced_at,
                    is_archived,
                    created_at
                FROM sync_state
                WHERE outlook_task_id = ?
                """,
                (task_id,),
            )
            
            row = cursor.fetchone()
            if row:
                return SyncState.from_row(row)
            return None
    
    def get_all(self, include_archived: bool = False) -> list[SyncState]:
        """
        Get all sync states.
        
        Args:
            include_archived: Whether to include archived assignments
            
        Returns:
            List of all SyncState records
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if include_archived:
                cursor.execute(
                    """
                    SELECT 
                        canvas_course_id,
                        canvas_assignment_id,
                        outlook_task_id,
                        last_seen_submission_state,
                        last_seen_due_date,
                        last_seen_title,
                        last_synced_at,
                        is_archived,
                        created_at
                    FROM sync_state
                    ORDER BY canvas_course_id, canvas_assignment_id
                    """
                )
            else:
                cursor.execute(
                    """
                    SELECT 
                        canvas_course_id,
                        canvas_assignment_id,
                        outlook_task_id,
                        last_seen_submission_state,
                        last_seen_due_date,
                        last_seen_title,
                        last_synced_at,
                        is_archived,
                        created_at
                    FROM sync_state
                    WHERE is_archived = 0
                    ORDER BY canvas_course_id, canvas_assignment_id
                    """
                )
            
            return [SyncState.from_row(row) for row in cursor.fetchall()]
    
    def save(self, state: SyncState) -> SyncState:
        """
        Save or update sync state.
        
        Uses INSERT OR REPLACE for idempotent upsert.
        
        Args:
            state: SyncState to save
            
        Returns:
            Saved SyncState with updated timestamps
        """
        now = datetime.utcnow()
        
        # Set timestamps
        if state.created_at is None:
            state = SyncState(
                canvas_course_id=state.canvas_course_id,
                canvas_assignment_id=state.canvas_assignment_id,
                outlook_task_id=state.outlook_task_id,
                last_seen_submission_state=state.last_seen_submission_state,
                last_seen_due_date=state.last_seen_due_date,
                last_seen_title=state.last_seen_title,
                last_synced_at=now,
                is_archived=state.is_archived,
                created_at=now,
            )
        else:
            state = SyncState(
                canvas_course_id=state.canvas_course_id,
                canvas_assignment_id=state.canvas_assignment_id,
                outlook_task_id=state.outlook_task_id,
                last_seen_submission_state=state.last_seen_submission_state,
                last_seen_due_date=state.last_seen_due_date,
                last_seen_title=state.last_seen_title,
                last_synced_at=now,
                is_archived=state.is_archived,
                created_at=state.created_at,
            )
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO sync_state (
                    canvas_course_id,
                    canvas_assignment_id,
                    outlook_task_id,
                    last_seen_submission_state,
                    last_seen_due_date,
                    last_seen_title,
                    last_synced_at,
                    is_archived,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.canvas_course_id,
                    state.canvas_assignment_id,
                    state.outlook_task_id,
                    state.last_seen_submission_state,
                    state.last_seen_due_date,
                    state.last_seen_title,
                    state.last_synced_at.isoformat() if state.last_synced_at else None,
                    1 if state.is_archived else 0,
                    state.created_at.isoformat() if state.created_at else None,
                ),
            )
            conn.commit()
        
        logger.debug(
            f"Saved state for assignment {state.canvas_course_id}:{state.canvas_assignment_id}"
        )
        return state
    
    def archive(self, course_id: int, assignment_id: int) -> bool:
        """
        Mark an assignment as archived.
        
        Does NOT delete the record or Outlook task.
        
        Args:
            course_id: Canvas course ID
            assignment_id: Canvas assignment ID
            
        Returns:
            True if record was updated, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE sync_state
                SET is_archived = 1, last_synced_at = ?
                WHERE canvas_course_id = ? AND canvas_assignment_id = ?
                """,
                (datetime.utcnow().isoformat(), course_id, assignment_id),
            )
            conn.commit()
            
            updated = cursor.rowcount > 0
            
        if updated:
            logger.info(f"Archived assignment {course_id}:{assignment_id}")
        
        return updated
    
    def get_synced_assignment_keys(self) -> set[tuple[int, int]]:
        """
        Get all (course_id, assignment_id) pairs that have been synced.
        
        Returns:
            Set of (course_id, assignment_id) tuples
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT canvas_course_id, canvas_assignment_id
                FROM sync_state
                WHERE outlook_task_id IS NOT NULL AND is_archived = 0
                """
            )
            
            return {(row[0], row[1]) for row in cursor.fetchall()}
    
    def count(self, include_archived: bool = False) -> int:
        """
        Count total sync state records.
        
        Args:
            include_archived: Whether to include archived records
            
        Returns:
            Total record count
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if include_archived:
                cursor.execute("SELECT COUNT(*) FROM sync_state")
            else:
                cursor.execute("SELECT COUNT(*) FROM sync_state WHERE is_archived = 0")
            
            return cursor.fetchone()[0]
    
    def clear(self) -> None:
        """
        Clear all sync state.
        
        WARNING: This is destructive. Use only for testing or reset.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sync_state")
            conn.commit()
        
        logger.warning("All sync state cleared")
