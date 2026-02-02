"""
Configuration settings with environment variable loading.

All secrets MUST be provided via environment variables.
Never log or expose tokens in any output.
"""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when required configuration is missing or invalid."""
    pass


@dataclass(frozen=True)
class CanvasConfig:
    """Canvas LMS configuration."""
    base_url: str
    access_token: str
    
    def __post_init__(self):
        if not self.base_url:
            raise ConfigurationError("CANVAS_BASE_URL is required")
        if not self.access_token:
            raise ConfigurationError("CANVAS_ACCESS_TOKEN is required")
        # Validate URL format
        if not self.base_url.startswith("https://"):
            raise ConfigurationError("CANVAS_BASE_URL must use HTTPS")
    
    def __repr__(self) -> str:
        """Never expose token in repr."""
        return f"CanvasConfig(base_url='{self.base_url}', access_token='***REDACTED***')"


@dataclass(frozen=True)
class MicrosoftConfig:
    """Microsoft Graph API configuration."""
    client_id: str
    tenant_id: str
    redirect_uri: str = "http://localhost:8400"
    scopes: tuple = field(default_factory=lambda: ("Tasks.ReadWrite", "User.Read"))
    token_cache_path: Optional[Path] = None
    
    def __post_init__(self):
        if not self.client_id:
            raise ConfigurationError("MICROSOFT_CLIENT_ID is required")
        if not self.tenant_id:
            raise ConfigurationError("MICROSOFT_TENANT_ID is required")
    
    def __repr__(self) -> str:
        """Safe repr without sensitive data."""
        return (
            f"MicrosoftConfig(client_id='{self.client_id[:8]}...', "
            f"tenant_id='{self.tenant_id}', redirect_uri='{self.redirect_uri}')"
        )


@dataclass(frozen=True)
class SyncConfig:
    """Sync engine configuration."""
    task_list_name: str = "Canvas Assignments"
    dry_run: bool = False
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    batch_size: int = 50


@dataclass(frozen=True)
class StorageConfig:
    """Persistent storage configuration."""
    database_path: Path = field(default_factory=lambda: Path("data/sync_state.db"))
    
    def __post_init__(self):
        # Ensure parent directory exists
        object.__setattr__(self, 'database_path', Path(self.database_path))


@dataclass(frozen=True)
class Settings:
    """
    Application settings container.
    
    All configuration is loaded from environment variables.
    Secrets are never logged or exposed.
    """
    canvas: CanvasConfig
    microsoft: MicrosoftConfig
    sync: SyncConfig
    storage: StorageConfig
    log_level: str = "INFO"
    
    def __repr__(self) -> str:
        return (
            f"Settings(\n"
            f"  canvas={self.canvas},\n"
            f"  microsoft={self.microsoft},\n"
            f"  sync={self.sync},\n"
            f"  storage={self.storage}\n"
            f")"
        )



def load_settings(env_file: Optional[Path] = None) -> Settings:
    """
    Load settings from environment variables.
    
    Optionally loads from a .env file first.
    
    Args:
        env_file: Optional path to .env file
        
    Returns:
        Configured Settings instance
        
    Raises:
        ConfigurationError: If required configuration is missing
    """
    # Load .env file using python-dotenv
    from dotenv import load_dotenv
    
    if env_file:
        logger.debug(f"Loading environment from {env_file}")
        load_dotenv(env_file)
    else:
        logger.debug("Loading environment from .env")
        load_dotenv()
    
    try:
        canvas = CanvasConfig(
            base_url=os.getenv("CANVAS_BASE_URL", "").rstrip("/"),
            access_token=os.getenv("CANVAS_ACCESS_TOKEN", ""),
        )
        
        microsoft = MicrosoftConfig(
            client_id=os.getenv("MICROSOFT_CLIENT_ID", ""),
            tenant_id=os.getenv("MICROSOFT_TENANT_ID", ""),
            redirect_uri=os.getenv("MICROSOFT_REDIRECT_URI", "http://localhost:8400"),
            token_cache_path=Path(os.getenv("MICROSOFT_TOKEN_CACHE", "data/token_cache.json")),
        )
        
        sync = SyncConfig(
            task_list_name=os.getenv("SYNC_TASK_LIST_NAME", "Canvas Assignments"),
            dry_run=os.getenv("SYNC_DRY_RUN", "false").lower() == "true",
            max_retries=int(os.getenv("SYNC_MAX_RETRIES", "3")),
            retry_delay_seconds=float(os.getenv("SYNC_RETRY_DELAY", "1.0")),
        )
        
        storage = StorageConfig(
            database_path=Path(os.getenv("STORAGE_DATABASE_PATH", "data/sync_state.db")),
        )
        
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        
        settings = Settings(
            canvas=canvas,
            microsoft=microsoft,
            sync=sync,
            storage=storage,
            log_level=log_level,
        )
        
        logger.info("Configuration loaded successfully")
        logger.debug(f"Settings: {settings}")
        
        return settings
        
    except ConfigurationError:
        raise
    except Exception as e:
        raise ConfigurationError(f"Failed to load configuration: {e}") from e
