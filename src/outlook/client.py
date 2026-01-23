"""
Microsoft Graph API client for Outlook Tasks.

Handles OAuth 2.0 authentication via MSAL with token caching.
Provides operations for task lists and tasks.
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

import msal
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import OutlookTask, TaskList, TaskStatus

logger = logging.getLogger(__name__)


class GraphAPIError(Exception):
    """Raised when Microsoft Graph API returns an error."""
    
    def __init__(
        self, 
        message: str, 
        status_code: Optional[int] = None, 
        error_code: Optional[str] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class AuthenticationError(GraphAPIError):
    """Raised when authentication fails."""
    pass


class OutlookClient:
    """
    Client for Microsoft Graph API - Outlook Tasks (Microsoft To Do).
    
    Features:
    - OAuth 2.0 authentication with MSAL
    - Token caching and refresh
    - Retry logic for transient failures
    - Rate limiting handling
    
    Usage:
        client = OutlookClient(
            client_id="...",
            tenant_id="...",
            token_cache_path=Path("token_cache.json"),
        )
        
        # Authenticate (interactive on first run)
        client.authenticate()
        
        # Get or create task list
        task_list = client.get_or_create_task_list("Canvas Assignments")
        
        # Create a task
        task = OutlookTask(title="Complete homework", status=TaskStatus.NOT_STARTED)
        created_task = client.create_task(task_list.id, task)
    """
    
    GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
    TASK_LISTS_ENDPOINT = "/me/todo/lists"
    TASKS_ENDPOINT = "/me/todo/lists/{list_id}/tasks"
    TASK_ENDPOINT = "/me/todo/lists/{list_id}/tasks/{task_id}"
    
    def __init__(
        self,
        client_id: str,
        tenant_id: str,
        redirect_uri: str = "http://localhost:8400",
        scopes: tuple[str, ...] = ("Tasks.ReadWrite", "User.Read"),
        token_cache_path: Optional[Path] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """
        Initialize Outlook client.
        
        Args:
            client_id: Azure AD application client ID
            tenant_id: Azure AD tenant ID
            redirect_uri: OAuth redirect URI
            scopes: Required Microsoft Graph scopes
            token_cache_path: Path to token cache file
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        self.client_id = client_id
        self.tenant_id = tenant_id
        self.redirect_uri = redirect_uri
        self.scopes = list(scopes)
        self.token_cache_path = token_cache_path
        self.timeout = timeout
        
        # Initialize MSAL token cache
        self._token_cache = msal.SerializableTokenCache()
        if self.token_cache_path and self.token_cache_path.exists():
            logger.debug(f"Loading token cache from {self.token_cache_path}")
            self._token_cache.deserialize(self.token_cache_path.read_text())
        
        # Initialize MSAL public client
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        self._msal_app = msal.PublicClientApplication(
            client_id,
            authority=authority,
            token_cache=self._token_cache,
        )
        
        self._access_token: Optional[str] = None
        
        # Configure HTTP session with retry logic
        self._session = requests.Session()
        
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PATCH", "DELETE"],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self._session.mount("https://", adapter)
        
        logger.info(f"Outlook client initialized for tenant {tenant_id}")
    
    def __repr__(self) -> str:
        return f"OutlookClient(client_id='{self.client_id[:8]}...', tenant_id='{self.tenant_id}')"
    
    def _save_token_cache(self) -> None:
        """Persist token cache to disk."""
        if self.token_cache_path and self._token_cache.has_state_changed:
            self.token_cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_cache_path.write_text(self._token_cache.serialize())
            logger.debug("Token cache saved")
    
    def authenticate(self) -> None:
        """
        Authenticate with Microsoft Graph API.
        
        Attempts silent authentication first using cached tokens.
        Falls back to interactive authentication if needed.
        
        Raises:
            AuthenticationError: If authentication fails
        """
        logger.info("Authenticating with Microsoft Graph...")
        
        # Try silent authentication first
        accounts = self._msal_app.get_accounts()
        if accounts:
            logger.debug(f"Found {len(accounts)} cached account(s), attempting silent auth")
            result = self._msal_app.acquire_token_silent(
                self.scopes,
                account=accounts[0],
            )
            
            if result and "access_token" in result:
                self._access_token = result["access_token"]
                self._save_token_cache()
                logger.info("Silent authentication successful")
                return
            
            if result and "error" in result:
                logger.warning(f"Silent auth failed: {result.get('error_description')}")
        
        # Interactive authentication required
        logger.info("Interactive authentication required. Opening browser...")
        
        result = self._msal_app.acquire_token_interactive(
            scopes=self.scopes,
            redirect_uri=self.redirect_uri,
        )
        
        if "access_token" in result:
            self._access_token = result["access_token"]
            self._save_token_cache()
            logger.info("Interactive authentication successful")
        else:
            error_msg = result.get("error_description", result.get("error", "Unknown error"))
            logger.error(f"Authentication failed: {error_msg}")
            raise AuthenticationError(f"Authentication failed: {error_msg}")
    
    def _ensure_authenticated(self) -> None:
        """Ensure we have a valid access token."""
        if not self._access_token:
            raise AuthenticationError("Not authenticated. Call authenticate() first.")
    
    def _get_headers(self) -> dict[str, str]:
        """Get request headers with authorization."""
        self._ensure_authenticated()
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict | list | None:
        """
        Make authenticated request to Microsoft Graph API.
        
        Args:
            method: HTTP method (GET, POST, PATCH, DELETE)
            endpoint: API endpoint
            data: Request body (for POST/PATCH)
            params: Query parameters
            
        Returns:
            Parsed JSON response, or None for 204 responses
            
        Raises:
            GraphAPIError: If request fails
        """
        url = f"{self.GRAPH_BASE_URL}{endpoint}"
        
        try:
            response = self._session.request(
                method=method,
                url=url,
                headers=self._get_headers(),
                json=data,
                params=params,
                timeout=self.timeout,
            )
            
            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.warning(f"Rate limited. Waiting {retry_after} seconds...")
                time.sleep(retry_after)
                return self._make_request(method, endpoint, data, params)
            
            # Handle token refresh needed
            if response.status_code == 401:
                logger.info("Token expired, refreshing...")
                self._access_token = None
                self.authenticate()
                return self._make_request(method, endpoint, data, params)
            
            response.raise_for_status()
            
            # Handle 204 No Content
            if response.status_code == 204:
                return None
            
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"Graph API error: {e}"
            error_code = None
            
            try:
                error_body = e.response.json()
                if "error" in error_body:
                    error_msg = f"Graph API error: {error_body['error'].get('message', str(e))}"
                    error_code = error_body["error"].get("code")
            except (ValueError, AttributeError):
                pass
            
            logger.error(error_msg)
            raise GraphAPIError(
                error_msg,
                status_code=e.response.status_code if e.response else None,
                error_code=error_code,
            ) from e
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Graph request failed: {e}"
            logger.error(error_msg)
            raise GraphAPIError(error_msg) from e
    
    # ============================================================
    # Task List Operations
    # ============================================================
    
    def get_task_lists(self) -> list[TaskList]:
        """
        Fetch all task lists.
        
        Returns:
            List of TaskList objects
        """
        logger.debug("Fetching task lists...")
        
        response = self._make_request("GET", self.TASK_LISTS_ENDPOINT)
        
        task_lists = []
        for item in response.get("value", []):
            task_lists.append(TaskList.from_api_response(item))
        
        logger.debug(f"Found {len(task_lists)} task lists")
        return task_lists
    
    def create_task_list(self, name: str) -> TaskList:
        """
        Create a new task list.
        
        Args:
            name: Display name for the task list
            
        Returns:
            Created TaskList object
        """
        logger.info(f"Creating task list: {name}")
        
        response = self._make_request(
            "POST",
            self.TASK_LISTS_ENDPOINT,
            data={"displayName": name},
        )
        
        return TaskList.from_api_response(response)
    
    def get_or_create_task_list(self, name: str) -> TaskList:
        """
        Get existing task list by name, or create if not exists.
        
        This is the primary method for getting the sync target list.
        
        Args:
            name: Task list name
            
        Returns:
            TaskList object (existing or newly created)
        """
        logger.debug(f"Looking for task list: {name}")
        
        task_lists = self.get_task_lists()
        
        for task_list in task_lists:
            if task_list.display_name == name:
                logger.debug(f"Found existing task list: {task_list.id}")
                return task_list
        
        # Create new list
        return self.create_task_list(name)
    
    # ============================================================
    # Task Operations
    # ============================================================
    
    def get_tasks(self, list_id: str) -> list[OutlookTask]:
        """
        Fetch all tasks in a task list.
        
        Args:
            list_id: Task list ID
            
        Returns:
            List of OutlookTask objects
        """
        logger.debug(f"Fetching tasks for list {list_id}")
        
        endpoint = self.TASKS_ENDPOINT.format(list_id=list_id)
        
        all_tasks = []
        next_link = endpoint
        
        while next_link:
            if next_link.startswith("http"):
                # Full URL from @odata.nextLink
                response = self._session.get(
                    next_link,
                    headers=self._get_headers(),
                    timeout=self.timeout,
                ).json()
            else:
                response = self._make_request("GET", next_link)
            
            for item in response.get("value", []):
                all_tasks.append(OutlookTask.from_api_response(item))
            
            next_link = response.get("@odata.nextLink")
        
        logger.debug(f"Found {len(all_tasks)} tasks")
        return all_tasks
    
    def get_task(self, list_id: str, task_id: str) -> Optional[OutlookTask]:
        """
        Fetch a specific task.
        
        Args:
            list_id: Task list ID
            task_id: Task ID
            
        Returns:
            OutlookTask object, or None if not found
        """
        endpoint = self.TASK_ENDPOINT.format(list_id=list_id, task_id=task_id)
        
        try:
            response = self._make_request("GET", endpoint)
            return OutlookTask.from_api_response(response)
        except GraphAPIError as e:
            if e.status_code == 404:
                return None
            raise
    
    def create_task(self, list_id: str, task: OutlookTask) -> OutlookTask:
        """
        Create a new task.
        
        Args:
            list_id: Task list ID
            task: Task to create
            
        Returns:
            Created task with ID populated
        """
        logger.info(f"Creating task: {task.title}")
        
        endpoint = self.TASKS_ENDPOINT.format(list_id=list_id)
        
        response = self._make_request(
            "POST",
            endpoint,
            data=task.to_api_payload(),
        )
        
        return OutlookTask.from_api_response(response)
    
    def update_task(
        self, 
        list_id: str, 
        task_id: str, 
        updates: dict,
    ) -> OutlookTask:
        """
        Update an existing task.
        
        Only sends the fields that need updating (minimal payload).
        
        Args:
            list_id: Task list ID
            task_id: Task ID
            updates: Dictionary of field changes
            
        Returns:
            Updated task
        """
        logger.info(f"Updating task {task_id}: {list(updates.keys())}")
        
        endpoint = self.TASK_ENDPOINT.format(list_id=list_id, task_id=task_id)
        
        # Build minimal payload
        payload = {}
        
        if "title" in updates:
            payload["title"] = updates["title"]
        
        if "status" in updates:
            status = updates["status"]
            if isinstance(status, TaskStatus):
                payload["status"] = status.value
            else:
                payload["status"] = status
        
        if "due_date" in updates:
            due = updates["due_date"]
            if due:
                payload["dueDateTime"] = {
                    "dateTime": f"{due.isoformat()}T00:00:00",
                    "timeZone": "UTC",
                }
            else:
                payload["dueDateTime"] = None
        
        if "body_content" in updates:
            payload["body"] = {
                "content": updates["body_content"],
                "contentType": "text",
            }
        
        response = self._make_request("PATCH", endpoint, data=payload)
        
        return OutlookTask.from_api_response(response)
    
    def complete_task(self, list_id: str, task_id: str) -> OutlookTask:
        """
        Mark a task as completed.
        
        Args:
            list_id: Task list ID
            task_id: Task ID
            
        Returns:
            Updated task
        """
        logger.info(f"Marking task {task_id} as completed")
        return self.update_task(list_id, task_id, {"status": TaskStatus.COMPLETED})
    
    def reopen_task(self, list_id: str, task_id: str) -> OutlookTask:
        """
        Reopen a completed task.
        
        Args:
            list_id: Task list ID
            task_id: Task ID
            
        Returns:
            Updated task
        """
        logger.info(f"Reopening task {task_id}")
        return self.update_task(list_id, task_id, {"status": TaskStatus.NOT_STARTED})
    
    def delete_task(self, list_id: str, task_id: str) -> None:
        """
        Delete a task.
        
        Note: For sync purposes, prefer archiving over deletion.
        
        Args:
            list_id: Task list ID
            task_id: Task ID
        """
        logger.info(f"Deleting task {task_id}")
        
        endpoint = self.TASK_ENDPOINT.format(list_id=list_id, task_id=task_id)
        self._make_request("DELETE", endpoint)
    
    def close(self) -> None:
        """Close the HTTP session and save token cache."""
        self._save_token_cache()
        self._session.close()
        logger.debug("Outlook client session closed")
    
    def __enter__(self) -> "OutlookClient":
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
