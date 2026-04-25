"""
Generate professional headshot from casual photo using Kie.ai API.

Usage:
    python tools/generate_headshot.py <input_image_path> [output_filename]
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

from kie_api import KieAPI, KieAPIError, GenerationError, TimeoutError

load_dotenv()

# Configuration
API_KEY = os.getenv("KIE_API_KEY")
UPLOAD_URL = "https://kieai.redpandaai.co"
MODEL = "nano-banana-2"

# Paths
INPUT_DIR = Path("headshot-input-images")
OUTPUT_DIR = Path("headshot-generated-images")

# System prompt for professional headshot
SYSTEM_PROMPT = """Transform this casual photo into a professional corporate headshot.

Keep the person's facial features, likeness, and identity exactly as they appear in the reference image.

Apply these changes:
- Change attire to a deep navy blue business suit over a white collared shirt
- Use a head and shoulders framing with shoulders angled slightly to the left
- Set expression to confident and approachable with a slight natural smile
- Apply professional three-point studio lighting setup
- Set background to neutral light-gray studio backdrop
- Make it ultra-photorealistic with sharp focus on the eyes
- Create shallow depth of field like an 85mm f/1.4 portrait lens
- Apply professional color grading and natural skin retouching

Do NOT change: face shape, eye color, hair color, skin tone, facial structure.
Do NOT add: watermarks, signatures, text, cartoons, illustrations.
Keep the person's exact identity from the reference image."""


def validate_image(image_path: Path) -> tuple[bool, str]:
    """Validate the input image exists and is a supported format."""
    if not image_path.exists():
        return False, f"Image not found: {image_path}"

    valid_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    if image_path.suffix.lower() not in valid_extensions:
        return False, f"Unsupported format. Use: {', '.join(valid_extensions)}"

    file_size_mb = image_path.stat().st_size / (1024 * 1024)
    if file_size_mb > 10:
        return False, f"File too large ({file_size_mb:.1f}MB). Max 10MB allowed."

    return True, "Valid"


def upload_image(image_path: Path) -> str:
    """Upload image to Kie.ai and return the URL."""
    url = f"{UPLOAD_URL}/api/file-stream-upload"
    headers = {"Authorization": f"Bearer {API_KEY}"}

    with open(image_path, "rb") as f:
        files = {"file": (image_path.name, f, "image/png")}
        data = {"uploadPath": "headshot-inputs", "fileName": image_path.name}
        response = requests.post(url, headers=headers, files=files, data=data, timeout=60)

    response.raise_for_status()
    result = response.json()

    if result.get("code") and result.get("code") != 200:
        raise Exception(f"Upload failed: {result.get('msg', 'Unknown error')}")

    download_url = result.get("data", {}).get("downloadUrl")
    if not download_url:
        raise Exception(f"No download URL in upload response: {result}")

    print(f"Image uploaded: {download_url}")
    return download_url


def create_task(image_url: str, api_key: str) -> str:
    """Create headshot generation task via Kie.ai API."""
    url = "https://api.kie.ai/api/v1/jobs/createTask"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": MODEL,
        "input": {
            "prompt": SYSTEM_PROMPT,
            "image_input": [image_url],
            "aspect_ratio": "3:4",
            "resolution": "1K",
            "output_format": "png"
        }
    }

    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    result = response.json()

    task_data = result.get("data", {})
    task_id = task_data.get("taskId") if isinstance(task_data, dict) else None

    if not task_id:
        raise KieAPIError(f"Failed to create task: {result.get('msg', 'Unknown error')}")

    return task_id


def poll_for_result(task_id: str, api_key: str, max_retries: int = 30, delay: int = 5) -> dict:
    """Poll for task completion."""
    url = "https://api.kie.ai/api/v1/jobs/recordInfo"
    headers = {"Authorization": f"Bearer {api_key}"}

    for attempt in range(max_retries):
        response = requests.get(url, headers=headers, params={"taskId": task_id}, timeout=30)
        response.raise_for_status()
        result = response.json()

        data = result.get("data") or {}
        state = data.get("state") if isinstance(data, dict) else None

        if state == "success":
            return result
        elif state == "fail":
            fail_msg = data.get("failMsg", "Unknown error") if isinstance(data, dict) else "Unknown error"
            raise GenerationError(f"Task failed: {fail_msg}")

        print(f"Waiting for generation... ({attempt + 1}/{max_retries}) status: {state}")
        time.sleep(delay)

    raise TimeoutError("Task timed out after maximum retries")


def download_image(image_url: str, output_path: Path) -> None:
    """Download image from URL and save to file."""
    response = requests.get(image_url, timeout=60)
    response.raise_for_status()
    with open(output_path, "wb") as f:
        f.write(response.content)


def generate_headshot(input_image_path: str, output_filename: Optional[str] = None) -> Path:
    """
    Generate a professional headshot from a casual photo.

    Args:
        input_image_path: Path to the input casual photo.
        output_filename: Optional custom output filename.

    Returns:
        Path to the generated headshot image.
    """
    if not API_KEY:
        raise ValueError("KIE_API_KEY not found in environment variables")

    input_path = Path(input_image_path)

    valid, message = validate_image(input_path)
    if not valid:
        raise ValueError(f"Invalid input image: {message}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not output_filename:
        stem = input_path.stem
        output_filename = f"{stem}_headshot.png"
    elif not output_filename.endswith(".png"):
        output_filename += ".png"

    output_path = OUTPUT_DIR / output_filename

    print(f"Generating headshot from: {input_path}")
    print("This may take a few minutes...")

    image_url = upload_image(input_path)

    task_id = create_task(image_url, API_KEY)
    print(f"Task created: {task_id}")

    result = poll_for_result(task_id, API_KEY)

    result_data = result.get("data", {})
    result_json_str = result_data.get("resultJson", "{}")
    result_json = json.loads(result_json_str)
    result_urls = result_json.get("resultUrls", [])

    if not result_urls:
        raise GenerationError("No images in API response")

    download_image(result_urls[0], output_path)
    print(f"Headshot saved to: {output_path}")

    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/generate_headshot.py <input_image_path> [output_filename]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_name = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        result_path = generate_headshot(input_path, output_name)
        print(f"\nSuccess! Headshot generated at: {result_path}")
    except KieAPIError as e:
        print(f"API Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)