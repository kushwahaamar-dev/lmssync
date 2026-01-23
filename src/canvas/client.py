"""
Canvas LMS API client.

Handles authentication, pagination, and error handling for Canvas API.
All tokens are passed via configuration and never logged.
"""

import logging
import time
from typing import Iterator, Optional
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import Assignment, Course, Submission

logger = logging.getLogger(__name__)


class CanvasAPIError(Exception):
    """Raised when Canvas API returns an error."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, response: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class CanvasClient:
    """
    Client for Canvas LMS API.
    
    Handles:
    - Authentication via Personal Access Token
    - Automatic pagination
    - Retry logic for transient failures
    - Rate limiting respect
    
    Usage:
        client = CanvasClient(base_url="https://canvas.example.com", access_token="...")
        
        for course in client.get_active_courses():
            for assignment in client.get_assignments(course.id):
                print(assignment.name)
    """
    
    # API endpoints
    COURSES_ENDPOINT = "/api/v1/courses"
    ASSIGNMENTS_ENDPOINT = "/api/v1/courses/{course_id}/assignments"
    SUBMISSION_ENDPOINT = "/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/self"
    
    def __init__(
        self,
        base_url: str,
        access_token: str,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """
        Initialize Canvas client.
        
        Args:
            base_url: Canvas instance URL (e.g., https://canvas.instructure.com)
            access_token: Personal Access Token (never logged)
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts for transient failures
        """
        self.base_url = base_url.rstrip("/")
        self._access_token = access_token  # Private, never logged
        self.timeout = timeout
        
        # Configure session with retry logic
        self._session = requests.Session()
        
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        
        # Set default headers
        self._session.headers.update({
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        
        logger.info(f"Canvas client initialized for {self.base_url}")
    
    def __repr__(self) -> str:
        """Never expose token in repr."""
        return f"CanvasClient(base_url='{self.base_url}')"
    
    def _make_request(
        self,
        endpoint: str,
        params: Optional[dict] = None,
    ) -> dict | list:
        """
        Make authenticated request to Canvas API.
        
        Handles rate limiting and error responses.
        
        Args:
            endpoint: API endpoint path
            params: Query parameters
            
        Returns:
            Parsed JSON response
            
        Raises:
            CanvasAPIError: If request fails
        """
        url = urljoin(self.base_url, endpoint)
        
        try:
            response = self._session.get(
                url,
                params=params,
                timeout=self.timeout,
            )
            
            # Handle rate limiting
            if response.status_code == 403:
                rate_limit_remaining = response.headers.get("X-Rate-Limit-Remaining")
                if rate_limit_remaining and float(rate_limit_remaining) < 1:
                    logger.warning("Rate limited, waiting before retry...")
                    time.sleep(10)
                    return self._make_request(endpoint, params)
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"Canvas API error: {e}"
            try:
                error_body = e.response.json()
                if "errors" in error_body:
                    error_msg = f"Canvas API error: {error_body['errors']}"
            except (ValueError, AttributeError):
                pass
            
            logger.error(error_msg)
            raise CanvasAPIError(
                error_msg,
                status_code=e.response.status_code if e.response else None,
            ) from e
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Canvas request failed: {e}"
            logger.error(error_msg)
            raise CanvasAPIError(error_msg) from e
    
    def _paginate(
        self,
        endpoint: str,
        params: Optional[dict] = None,
    ) -> Iterator[dict]:
        """
        Handle Canvas API pagination.
        
        Canvas uses Link headers for pagination.
        
        Args:
            endpoint: API endpoint
            params: Query parameters
            
        Yields:
            Individual items from paginated response
        """
        params = params or {}
        params.setdefault("per_page", 100)  # Max allowed
        
        url = urljoin(self.base_url, endpoint)
        
        while url:
            try:
                response = self._session.get(
                    url,
                    params=params if url == urljoin(self.base_url, endpoint) else None,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                
                data = response.json()
                
                if isinstance(data, list):
                    yield from data
                else:
                    yield data
                
                # Get next page from Link header
                url = None
                link_header = response.headers.get("Link", "")
                for link in link_header.split(","):
                    if 'rel="next"' in link:
                        url = link.split(";")[0].strip(" <>")
                        break
                        
            except requests.exceptions.RequestException as e:
                logger.error(f"Pagination request failed: {e}")
                raise CanvasAPIError(f"Pagination failed: {e}") from e
    
    def get_active_courses(self) -> list[Course]:
        """
        Fetch all active courses for the current user.
        
        Returns:
            List of active Course objects
        """
        logger.info("Fetching active courses...")
        
        courses = []
        for course_data in self._paginate(
            self.COURSES_ENDPOINT,
            params={"enrollment_state": "active"},
        ):
            try:
                course = Course.from_api_response(course_data)
                courses.append(course)
                logger.debug(f"Found course: {course.name} (ID: {course.id})")
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping malformed course data: {e}")
                continue
        
        logger.info(f"Found {len(courses)} active courses")
        return courses
    
    def get_assignments(self, course: Course) -> list[Assignment]:
        """
        Fetch all assignments for a course with submission status.
        
        Args:
            course: Course to fetch assignments for
            
        Returns:
            List of Assignment objects with submission status
        """
        logger.info(f"Fetching assignments for course: {course.name}")
        
        endpoint = self.ASSIGNMENTS_ENDPOINT.format(course_id=course.id)
        
        assignments = []
        for assignment_data in self._paginate(
            endpoint,
            params={"include[]": "submission"},
        ):
            try:
                # Skip unpublished assignments
                if not assignment_data.get("published", True):
                    logger.debug(f"Skipping unpublished assignment: {assignment_data.get('name')}")
                    continue
                
                # Extract submission if included
                submission = None
                if "submission" in assignment_data and assignment_data["submission"]:
                    submission = Submission.from_api_response(assignment_data["submission"])
                
                assignment = Assignment.from_api_response(
                    assignment_data,
                    course_id=course.id,
                    course_name=course.name,
                    submission=submission,
                )
                assignments.append(assignment)
                
                logger.debug(
                    f"Found assignment: {assignment.name} "
                    f"(submitted: {assignment.is_submitted})"
                )
                
            except (KeyError, ValueError) as e:
                logger.warning(
                    f"Skipping malformed assignment data: {e}"
                )
                continue
        
        logger.info(f"Found {len(assignments)} assignments in {course.name}")
        return assignments
    
    def get_submission(self, course_id: int, assignment_id: int) -> Optional[Submission]:
        """
        Fetch submission status for a specific assignment.
        
        Use this for targeted refresh of submission status.
        
        Args:
            course_id: Course ID
            assignment_id: Assignment ID
            
        Returns:
            Submission object, or None if no submission exists
        """
        logger.debug(f"Fetching submission for assignment {assignment_id} in course {course_id}")
        
        endpoint = self.SUBMISSION_ENDPOINT.format(
            course_id=course_id,
            assignment_id=assignment_id,
        )
        
        try:
            data = self._make_request(endpoint)
            return Submission.from_api_response(data)
        except CanvasAPIError as e:
            if e.status_code == 404:
                return None
            raise
    
    def get_all_assignments(self) -> list[Assignment]:
        """
        Fetch all assignments from all active courses.
        
        Convenience method that combines course and assignment fetching.
        
        Returns:
            List of all Assignment objects with submission status
        """
        all_assignments = []
        
        courses = self.get_active_courses()
        for course in courses:
            assignments = self.get_assignments(course)
            all_assignments.extend(assignments)
        
        logger.info(f"Total assignments across all courses: {len(all_assignments)}")
        return all_assignments
    
    def close(self) -> None:
        """Close the HTTP session."""
        self._session.close()
        logger.debug("Canvas client session closed")
    
    def __enter__(self) -> "CanvasClient":
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
