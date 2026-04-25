"""
Kie.ai API Client — Shared wrapper for image generation services.

Provides a unified interface for:
- Task creation and polling
- Image download
- Error handling with custom exceptions

Usage:
    from tools.kie_api import KieAPI, KieAPIError, AuthenticationError

    kie = KieAPI()
    result = kie.generate_image(prompt, save_path, reference_images=[url])
"""

import os
import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

import requests
from dotenv import load_dotenv

load_dotenv()


# =============================================================================
# EXCEPTIONS
# =============================================================================

class KieAPIError(Exception):
    """Base exception for Kie API errors."""
    pass


class AuthenticationError(KieAPIError):
    """Invalid or missing API key."""
    pass


class RateLimitError(KieAPIError):
    """API rate limit exceeded."""
    pass


class APIError(KieAPIError):
    """General API error."""
    pass


class GenerationError(KieAPIError):
    """Image generation failed."""
    pass


class TimeoutError(KieAPIError):
    """Task did not complete in time."""
    pass


# =============================================================================
# CLIENT
# =============================================================================

class KieAPI:
    """
    Unified client for Kie.ai image generation API.

    Args:
        api_key: Kie.ai API key. If None, loads from KIE_API_KEY env var.
        model: Model name. Defaults to env or "nano-banana-2".
        resolution: Image resolution (1K, 2K, 4K). Defaults to env or "2K".
        aspect_ratio: Aspect ratio (e.g., "1:1", "4:5"). Defaults to env or "4:5".
        output_format: Output format (png, jpg). Defaults to "png".
        polling_interval: Seconds between status checks. Default 15.
        polling_max_retries: Max polling attempts. Default 240.
        polling_backoff: Multiplier for interval on each retry. Default 1.0.
    """

    DEFAULT_MODEL = "nano-banana-2"
    DEFAULT_RESOLUTION = "2K"
    DEFAULT_ASPECT_RATIO = "4:5"
    DEFAULT_OUTPUT_FORMAT = "png"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        resolution: Optional[str] = None,
        aspect_ratio: Optional[str] = None,
        output_format: Optional[str] = None,
        polling_interval: int = 5,
        polling_max_retries: int = 240,
        polling_backoff: float = 1.0,
    ):
        self.api_key = api_key or os.getenv("KIE_API_KEY")
        if not self.api_key:
            raise ValueError("KIE_API_KEY not found. Set it in .env or pass api_key parameter.")

        self.base_url = "https://api.kie.ai"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        self.model = model or os.getenv("KIE_MODEL", self.DEFAULT_MODEL)
        self.resolution = resolution or os.getenv("KIE_RESOLUTION", self.DEFAULT_RESOLUTION)
        self.aspect_ratio = aspect_ratio or os.getenv("KIE_ASPECT_RATIO", self.DEFAULT_ASPECT_RATIO)
        self.output_format = output_format or os.getenv("KIE_OUTPUT_FORMAT", self.DEFAULT_OUTPUT_FORMAT)

        self.polling_interval = polling_interval
        self.polling_max_retries = polling_max_retries
        self.polling_backoff = polling_backoff

    def _handle_response_errors(self, response: requests.Response, context: str = "") -> None:
        """Raise appropriate exception based on status code."""
        if response.status_code == 401:
            raise AuthenticationError(f"Invalid Kie.ai API key. {context}")
        elif response.status_code == 429:
            raise RateLimitError(f"API rate limit exceeded. {context}")
        elif response.status_code != 200:
            raise APIError(f"HTTP {response.status_code}: {response.text[:200]}. {context}")

    def _parse_response(self, response: requests.Response, context: str = "") -> Dict[str, Any]:
        """Parse JSON response and check for API-level errors."""
        try:
            data = response.json()
        except json.JSONDecodeError:
            raise APIError(f"Invalid JSON response. {context}")

        code = data.get("code")
        if code is not None and code != 200:
            raise APIError(f"{data.get('msg', 'Unknown error')} (code={code}). {context}")

        return data

    def create_task(
        self,
        prompt: str,
        reference_images: Optional[List[str]] = None,
        aspect_ratio: Optional[str] = None,
        nsfw_checker: Optional[bool] = None,
        **kwargs,
    ) -> str:
        """
        Create an image generation task.

        Args:
            prompt: The generation prompt.
            reference_images: Optional list of image URLs to use as reference.
            aspect_ratio: Override default aspect ratio (e.g., "1:1", "4:5").
            nsfw_checker: Whether to enable NSFW filtering.
            **kwargs: Additional parameters passed to the API input.

        Returns:
            task_id: The ID of the created task.

        Raises:
            AuthenticationError: If API key is invalid.
            RateLimitError: If rate limited.
            APIError: If task creation fails.
        """
        endpoint = f"{self.base_url}/api/v1/jobs/createTask"

        payload = {
            "model": self.model,
            "input": {
                "prompt": prompt,
                "input_urls": reference_images if reference_images else [],
                "aspect_ratio": aspect_ratio or self.aspect_ratio,
            },
        }

        if nsfw_checker is not None:
            payload["input"]["nsfw_checker"] = nsfw_checker

        for key, value in kwargs.items():
            if value is not None:
                payload["input"][key] = value

        response = requests.post(endpoint, json=payload, headers=self.headers, timeout=60)
        self._handle_response_errors(response, "creating task")
        data = self._parse_response(response, "creating task")

        task_id = data.get("data", {}).get("taskId")
        if not task_id:
            raise APIError(f"No task ID in response: {data}")

        return task_id

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get the current status of an image generation task.

        Args:
            task_id: The task ID to check.

        Returns:
            Dict containing:
                - task_id: The task ID
                - state: Current state ("pending", "success", "fail", "unknown")
                - image_urls: List of result URLs if successful
                - raw_data: Full response data for debugging
        """
        endpoint = f"{self.base_url}/api/v1/jobs/recordInfo"
        params = {"taskId": task_id}

        response = requests.get(endpoint, params=params, headers=self.headers, timeout=60)
        self._handle_response_errors(response, f"checking status for {task_id[:12]}")
        data = self._parse_response(response, f"checking status for {task_id[:12]}")

        result_data = data.get("data", {}) if isinstance(data, dict) else {}
        state = result_data.get("state", "unknown") if isinstance(result_data, dict) else str(result_data)

        result = {
            "task_id": task_id,
            "state": state,
            "raw_data": result_data,
        }

        if state == "success":
            result_json_str = result_data.get("resultJson", "")
            if isinstance(result_json_str, str):
                try:
                    result_json = json.loads(result_json_str)
                except json.JSONDecodeError:
                    result_json = {}
            else:
                result_json = result_json_str
            result["image_urls"] = result_json.get("resultUrls", []) if isinstance(result_json, dict) else []

        return result

    def wait_for_completion(
        self,
        task_id: str,
        poll_interval: Optional[int] = None,
        max_retries: Optional[int] = None,
        on_state_change: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Poll until task completes or fails.

        Args:
            task_id: The task to wait for.
            poll_interval: Override default polling interval.
            max_retries: Override default max retries.
            on_state_change: Optional callback(state) for state transitions.

        Returns:
            Task result dict with image_urls on success.

        Raises:
            GenerationError: If task state is "fail".
            TimeoutError: If max retries exceeded.
        """
        interval = poll_interval or self.polling_interval
        max_attempts = max_retries or self.polling_max_retries
        attempt = 0
        last_state = None

        while attempt < max_attempts:
            status = self.get_task_status(task_id)
            current_state = status["state"]

            if current_state != last_state:
                if on_state_change:
                    on_state_change(current_state)
                last_state = current_state

            if current_state == "success":
                return status
            elif current_state == "fail":
                error_msg = status["raw_data"].get("error", "Unknown generation error") if isinstance(status["raw_data"], dict) else "Unknown generation error"
                raise GenerationError(f"Image generation failed: {error_msg}")

            interval *= self.polling_backoff
            attempt += 1
            time.sleep(interval)

        raise TimeoutError(f"Task {task_id[:12]}... did not complete within {max_attempts} attempts")

    def download_image(self, url: str, save_path: str | Path, overwrite: bool = False) -> str:
        """
        Download an image from a URL.

        Args:
            url: The image URL.
            save_path: Where to save the image.
            overwrite: Whether to overwrite existing file.

        Returns:
            Path to the downloaded file.

        Raises:
            FileExistsError: If file exists and overwrite=False.
            APIError: If download fails.
        """
        save_path = Path(save_path)

        if save_path.exists() and not overwrite:
            raise FileExistsError(f"File already exists: {save_path}")

        save_path.parent.mkdir(parents=True, exist_ok=True)

        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()

        with open(save_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return str(save_path)

    def generate_image(
        self,
        prompt: str,
        save_path: str | Path,
        reference_images: Optional[List[str]] = None,
        aspect_ratio: Optional[str] = None,
        wait_callback: Optional[callable] = None,
        **kwargs,
    ) -> str:
        """
        Complete workflow: create task, poll, and download.

        Args:
            prompt: Generation prompt.
            save_path: Output file path.
            reference_images: Optional list of reference image URLs.
            aspect_ratio: Override default aspect ratio.
            wait_callback: Optional callback for state changes.
            **kwargs: Additional parameters for task creation.

        Returns:
            Path to the downloaded image.

        Raises:
            GenerationError: If task fails.
            TimeoutError: If task doesn't complete.
        """
        task_id = self.create_task(
            prompt=prompt,
            reference_images=reference_images,
            aspect_ratio=aspect_ratio,
            **kwargs,
        )

        status = self.wait_for_completion(
            task_id,
            on_state_change=wait_callback,
        )

        image_urls = status.get("image_urls", [])
        if not image_urls:
            raise GenerationError(f"No image URLs in successful task response")

        return self.download_image(image_urls[0], save_path)