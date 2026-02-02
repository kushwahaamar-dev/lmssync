#!/usr/bin/env python3
"""
Canvas to Outlook Task Sync - Main Entry Point

Synchronizes Canvas LMS assignment completion status to Microsoft Outlook Tasks.

Usage:
    python -m src.main              # Full sync
    python -m src.main --dry-run    # Preview changes without applying
    python -m src.main --verbose    # Enable debug logging

Environment Variables Required:
    CANVAS_BASE_URL         - Canvas instance URL (e.g., https://canvas.instructure.com)
    CANVAS_ACCESS_TOKEN     - Canvas Personal Access Token
    MICROSOFT_CLIENT_ID     - Azure AD application client ID
    MICROSOFT_TENANT_ID     - Azure AD tenant ID

See .env.example for all configuration options.
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path for imports if running as script
if __name__ == "__main__" and __package__ is None:
    PROJECT_ROOT = Path(__file__).parent.parent
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import load_settings, ConfigurationError
from src.canvas.client import CanvasClient, CanvasAPIError
from src.outlook.client import OutlookClient, AuthenticationError, GraphAPIError
from src.storage.state_store import StateStore
from src.sync.engine import SyncEngine


def setup_logging(verbose: bool = False) -> None:
    """
    Configure logging for the application.
    
    Args:
        verbose: If True, enable DEBUG level logging
    """
    level = logging.DEBUG if verbose else logging.INFO
    
    # Configure root logger
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )
    
    # Reduce noise from external libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("msal").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Sync Canvas LMS assignments to Microsoft Outlook Tasks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m src.main                    # Full sync
    python -m src.main --dry-run          # Preview changes
    python -m src.main --verbose          # Debug output
    python -m src.main --env .env.local   # Use custom env file
    
For setup instructions, see README.md
        """,
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without making any modifications",
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose/debug logging",
    )
    
    parser.add_argument(
        "--env",
        type=Path,
        help="Path to .env file (default: .env in current directory)",
    )
    
    parser.add_argument(
        "--reset-auth",
        action="store_true",
        help="Clear cached Microsoft auth tokens and re-authenticate",
    )
    
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show sync status without performing sync",
    )
    
    return parser.parse_args()


def show_status(state_store: StateStore) -> None:
    """
    Display current sync status.
    
    Args:
        state_store: State store to query
    """
    logger = logging.getLogger(__name__)
    
    total = state_store.count(include_archived=True)
    active = state_store.count(include_archived=False)
    archived = total - active
    
    logger.info("=" * 50)
    logger.info("Sync Status")
    logger.info("=" * 50)
    logger.info(f"Total tracked assignments: {total}")
    logger.info(f"Active assignments:        {active}")
    logger.info(f"Archived assignments:      {archived}")
    
    # Show recent activity
    states = state_store.get_all(include_archived=False)
    
    submitted_count = sum(1 for s in states if s.was_submitted)
    pending_count = active - submitted_count
    
    logger.info(f"Submitted (completed):     {submitted_count}")
    logger.info(f"Pending (not completed):   {pending_count}")
    logger.info("=" * 50)


def main() -> int:
    """
    Main entry point.
    
    Returns:
        Exit code (0 for success, 1 for error)
    """
    args = parse_args()
    setup_logging(verbose=args.verbose)
    
    logger = logging.getLogger(__name__)
    
    logger.info("Canvas to Outlook Task Sync")
    logger.info("=" * 50)
    
    # Load configuration
    try:
        settings = load_settings(env_file=args.env)
        
        if args.dry_run:
            logger.info("DRY RUN MODE - No changes will be made")
        
    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Please check your .env file or environment variables")
        logger.error("See .env.example for required configuration")
        return 1
    
    # Handle reset-auth flag
    if args.reset_auth and settings.microsoft.token_cache_path:
        token_path = settings.microsoft.token_cache_path
        if token_path.exists():
            logger.info(f"Clearing token cache: {token_path}")
            token_path.unlink()
    
    # Initialize state store
    state_store = StateStore(settings.storage.database_path)
    
    # Handle status-only mode
    if args.status:
        show_status(state_store)
        return 0
    
    # Initialize clients
    canvas_client = None
    outlook_client = None
    
    try:
        # Canvas client
        logger.info("Initializing Canvas client...")
        canvas_client = CanvasClient(
            base_url=settings.canvas.base_url,
            access_token=settings.canvas.access_token,
            max_retries=settings.sync.max_retries,
        )
        
        # Outlook client
        logger.info("Initializing Outlook client...")
        outlook_client = OutlookClient(
            client_id=settings.microsoft.client_id,
            tenant_id=settings.microsoft.tenant_id,
            redirect_uri=settings.microsoft.redirect_uri,
            scopes=settings.microsoft.scopes,
            token_cache_path=settings.microsoft.token_cache_path,
            max_retries=settings.sync.max_retries,
        )
        
        # Authenticate with Microsoft
        logger.info("Authenticating with Microsoft Graph...")
        try:
            outlook_client.authenticate()
        except AuthenticationError as e:
            logger.error(f"Microsoft authentication failed: {e}")
            logger.error("Try running with --reset-auth to clear cached tokens")
            return 1
        
        # Create sync engine
        engine = SyncEngine(
            canvas_client=canvas_client,
            outlook_client=outlook_client,
            state_store=state_store,
            task_list_name=settings.sync.task_list_name,
            dry_run=args.dry_run or settings.sync.dry_run,
            max_retries=settings.sync.max_retries,
            retry_delay=settings.sync.retry_delay_seconds,
        )
        
        # Execute sync
        logger.info("Starting synchronization...")
        stats = engine.sync()
        
        # Report results
        logger.info("=" * 50)
        logger.info("Sync Summary")
        logger.info("=" * 50)
        logger.info(f"Assignments processed: {stats.total_assignments}")
        logger.info(f"Tasks created:         {stats.created}")
        logger.info(f"Tasks updated:         {stats.updated}")
        logger.info(f"Marked complete:       {stats.completed}")
        logger.info(f"Reopened:              {stats.reopened}")
        logger.info(f"Archived:              {stats.archived}")
        logger.info(f"Skipped (no change):   {stats.skipped}")
        logger.info(f"Errors:                {stats.errors}")
        logger.info("=" * 50)
        
        if stats.errors > 0:
            logger.warning("Some errors occurred during sync. Check logs above.")
            return 1
        
        logger.info("Sync completed successfully!")
        return 0
        
    except CanvasAPIError as e:
        logger.error(f"Canvas API error: {e}")
        return 1
    except GraphAPIError as e:
        logger.error(f"Microsoft Graph API error: {e}")
        return 1
    except KeyboardInterrupt:
        logger.info("Sync interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1
    finally:
        # Clean up
        if canvas_client:
            canvas_client.close()
        if outlook_client:
            outlook_client.close()


if __name__ == "__main__":
    sys.exit(main())
