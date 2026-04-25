"""
Carousel Sequential Generator - WAT Framework

Generates LinkedIn carousel slides sequentially:
1. Intro slide (via Kie.ai image-to-image)
2. Content slides one-by-one
3. CTA slide
4. All images saved to carousels/{topic_name}_{timestamp}/ folder

Usage:
    python tools/carousel_sequential.py --topic "AI Trends 2026" --slides '[{"heading": "Intro", "description": "Desc 1"}]'

CLI Args:
    --topic, -t     : Carousel topic/title (required)
    --slides, -s    : JSON array of slide objects: [{"heading": "...", "description": "..."}, ...] (required)
    --output, -o    : Output directory (default: carousels/)
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any

from dotenv import load_dotenv

from kie_api import KieAPI, KieAPIError

load_dotenv()


# =============================================================================
# CONFIGURATION
# =============================================================================

KIE_CONFIG = {
    "model": "gpt-image-2-image-to-image",
    "aspect_ratio": "1:1",
    "polling_interval": 5,
    "polling_max_retries": 240,
    "polling_backoff": 1.0,
}

TEMPLATES = {
    "intro": "https://i.ibb.co/mrpfz00G/carousel-intro-slide-template.png",
    "content": "https://i.ibb.co/MDnv28r9/carousel-content-slide-template.png",
    "cta": "https://i.ibb.co/nqSdc1RY/carousel-cta-slide.png",
}

OUTPUT_CONFIG = {
    "base_dir": "carousels",
    "format": "png",
}

# Seconds to wait between slide generations to reduce API load
DELAY_BETWEEN_SLIDES = 5


# =============================================================================
# GENERATOR
# =============================================================================

class CarouselSequentialGenerator:
    """Generate LinkedIn carousel slides sequentially using Kie.ai."""

    def __init__(
        self,
        topic: str,
        slides_content: List[Dict[str, str]],
        api_key: Optional[str] = None,
        output_dir: Optional[str] = None,
    ):
        """
        Initialize carousel generator.

        Args:
            topic: The topic/title of the carousel.
            slides_content: List of dicts with 'heading' and 'description' for each slide.
            api_key: Kie.ai API key. Uses env var if None.
            output_dir: Base output directory.
        """
        self.topic = topic
        self.slides_content = slides_content
        self.total_slides = len(slides_content) + 2  # intro + content + CTA
        self.displayed_total = self.total_slides - 1  # Exclude CTA from displayed count
        self.output_dir = Path(output_dir or OUTPUT_CONFIG["base_dir"])

        self.kie = KieAPI(
            api_key=api_key,
            model=KIE_CONFIG["model"],
            aspect_ratio=KIE_CONFIG["aspect_ratio"],
            polling_interval=KIE_CONFIG["polling_interval"],
            polling_max_retries=KIE_CONFIG["polling_max_retries"],
            polling_backoff=KIE_CONFIG["polling_backoff"],
        )

        self.topic_folder = self._create_topic_folder()

        self.generated_images: Dict[str, Any] = {
            "intro": None,
            "content": [],
            "cta": None,
        }

    def _create_topic_folder(self) -> Path:
        """Create output folder for this carousel."""
        safe_topic = self._sanitize_filename(self.topic)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_name = f"{safe_topic}_{timestamp}"
        folder_path = self.output_dir / folder_name
        folder_path.mkdir(parents=True, exist_ok=True)
        print(f"Created carousel folder: {folder_path}")
        return folder_path

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """Convert topic name to safe filename."""
        invalid_chars = '<>:"/\\|？*'
        for char in invalid_chars:
            name = name.replace(char, "_")
        return name.strip()[:50]

    def _build_intro_prompt(self) -> str:
        """Build the prompt for intro slide generation."""
        # Escape any quotes in the topic to prevent prompt injection
        escaped_topic = self.topic.replace('"', '\\"').replace("'", "\\'")
        return (
            f"Using the provided image as a direct template, perform these EXACT text replacements:\n"
            f"1. Replace the large placeholder text '[CONTENT HEADING]' with EXACTLY this text: \"{escaped_topic}\"\n"
            f"   - Preserve ALL characters exactly as shown including numbers like '$40', '40', 'billion'\n"
            f"   - Example: If topic is 'Google's $40 Billion Bet', write exactly 'Google's $40 Billion Bet' NOT 'Google's 0 Billion Bet'\n"
            f"2. Replace 'A [N]-slide breakdown' with 'A {self.displayed_total}-slide breakdown'\n"
            f"3. Replace the '[N]' inside the bottom right circle (the slide counter) with '0'\n"
            f"4. Replace the placeholder '[T]' inside the bottom right circle which is after '[N] / ' with '{self.displayed_total}'\n"
            f"IMPORTANT: Copy every character of the topic EXACTLY — do not change, autocorrect, or rephrase any text.\n"
            f"All other elements, fonts, colors, and the user avatar must remain unchanged."
        )

    def _build_content_prompt(self, slide_number: int, slide_counter: int, heading: str, description: str) -> str:
        """Build the prompt for a content slide."""
        # Escape quotes to prevent prompt injection
        escaped_heading = heading.replace('"', '\\"').replace("'", "\\'")
        escaped_description = description.replace('"', '\\"').replace("'", "\\'")
        return (
            f"Using the provided reference image, maintain the exact background, layout, colors, "
            f"and typography. Perform these EXACT text replacements:\n"
            f"1. Replace the giant text '0[N]' on the left side with '{slide_number:02d}'\n"
            f"2. Replace the bold serif text '[CONTENT HEADING]' with EXACTLY this heading: \"{escaped_heading}\"\n"
            f"   - Copy ALL characters exactly: '{heading}'\n"
            f"3. Replace the lighter text '[CONTENT DESCRIPTION]' with EXACTLY this description: \"{escaped_description}\"\n"
            f"   - Copy ALL characters exactly including numbers, $ symbols, punctuation\n"
            f"4. Replace the '[N]' inside the bottom right circle with '{slide_counter}'\n"
            f"5. Replace the '[T]' inside the bottom right circle which is after '[N] / ' with '{self.displayed_total}'\n"
            f"CRITICAL: Copy every character EXACTLY — '$40 billion' must appear as '$40 billion', not '$0 billion'.\n"
            f"Do not alter any other graphical elements, borders, or the remaining text."
        )

    def _build_cta_prompt(self) -> str:
        """Build the prompt for CTA slide generation."""
        cta_counter = self.displayed_total
        return (
            f"Using the provided reference image, maintain the exact background, layout, colors, "
            f"and typography. Apply the following precise text replacements: "
            f"1. Replace the '[N]' inside the bottom right circle with '{cta_counter}'. "
            f"2. Replace the '[T]' inside the bottom right circle which is after '[N] / ' with '{self.displayed_total}'. "
            f"Do not alter any other graphical elements, borders, or the remaining text."
        )

    def _generate_slide(
        self,
        prompt: str,
        filename: str,
        template_url: str,
        slide_description: str,
    ) -> Optional[str]:
        """Generate a single carousel slide using Kie.ai."""
        output_path = self.topic_folder / f"{filename}.{OUTPUT_CONFIG['format']}"

        print(f"\nGenerating {slide_description}...")
        print(f"  Output: {output_path.name}")
        print(f"  Model: {KIE_CONFIG['model']}")
        print(f"  Aspect Ratio: {KIE_CONFIG['aspect_ratio']}")

        try:
            def log_state(state: str):
                print(f"  Task status: {state}")

            result_path = self.kie.generate_image(
                prompt=prompt,
                save_path=str(output_path),
                reference_images=[template_url],
                aspect_ratio=KIE_CONFIG["aspect_ratio"],
                wait_callback=log_state,
            )
            print(f"  [OK] Generated: {result_path}")
            return result_path
        except KieAPIError as e:
            print(f"  [ERROR] Failed to generate {slide_description}: {e}")
            return None

    def generate_intro_slide(self) -> bool:
        """Generate the intro slide."""
        print(f"\n{'='*60}")
        print(f"Step 1: Generating Intro Slide")
        print(f"{'='*60}")
        print(f"  Topic: {self.topic}")
        print(f"  Total slides: {self.total_slides}")

        result_path = self._generate_slide(
            prompt=self._build_intro_prompt(),
            filename="0_intro",
            template_url=TEMPLATES["intro"],
            slide_description="intro slide",
        )

        if result_path:
            self.generated_images["intro"] = result_path
            return True
        return False

    def generate_content_slides(self) -> List[Dict[str, Any]]:
        """Generate all content slides sequentially."""
        print(f"\n{'='*60}")
        print(f"Step 2: Generating Content Slides (Sequentially)")
        print(f"{'='*60}")
        print(f"  Total content slides: {len(self.slides_content)}")

        results = []

        for i, slide_data in enumerate(self.slides_content, 1):
            slide_number = i
            slide_counter = i
            heading = slide_data.get("heading", f"Slide {i}")
            description = slide_data.get("description", "")

            print(f"\n--- Generating Slide {i}/{len(self.slides_content)} ---")

            if i > 1:
                print(f"  Waiting {DELAY_BETWEEN_SLIDES}s before next slide...")
                time.sleep(DELAY_BETWEEN_SLIDES)

            result_path = self._generate_slide(
                prompt=self._build_content_prompt(slide_number, slide_counter, heading, description),
                filename=f"{slide_number}_content",
                template_url=TEMPLATES["content"],
                slide_description=f"content slide #{i} ({heading[:40]}...)",
            )

            slide_result = {
                "slide_number": slide_number,
                "heading": heading,
                "path": result_path,
                "success": result_path is not None,
            }

            if result_path:
                self.generated_images["content"].append(result_path)

            results.append(slide_result)

        return results

    def generate_cta_slide(self) -> bool:
        """Generate the CTA slide."""
        print(f"\n{'='*60}")
        print(f"Step 3: Generating CTA Slide")
        print(f"{'='*60}")

        result_path = self._generate_slide(
            prompt=self._build_cta_prompt(),
            filename=f"{self.displayed_total}_cta",
            template_url=TEMPLATES["cta"],
            slide_description="CTA slide",
        )

        if result_path:
            self.generated_images["cta"] = result_path
            return True
        return False

    def _save_metadata(self, content_results: List[Dict[str, Any]]) -> str:
        """Save carousel metadata to JSON file."""
        all_slides = []
        if self.generated_images["intro"]:
            all_slides.append(self.generated_images["intro"])
        for r in content_results:
            if r["path"]:
                all_slides.append(r["path"])
        if self.generated_images["cta"]:
            all_slides.append(self.generated_images["cta"])

        metadata = {
            "topic": self.topic,
            "folder": str(self.topic_folder),
            "intro_slide": self.generated_images["intro"],
            "content_slides": [
                {"path": r["path"], "heading": r["heading"], "success": r["success"]}
                for r in content_results
            ],
            "cta_slide": self.generated_images["cta"],
            "all_slides": all_slides,
            "total_slides": len(all_slides),
            "generated_at": datetime.now().isoformat(),
        }

        metadata_path = self.topic_folder / "carousel_metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        print(f"\nMetadata saved to: {metadata_path}")
        return str(metadata_path)

    def generate_full_carousel(self) -> Dict[str, Any]:
        """Generate the complete carousel sequentially."""
        print(f"\n{'='*60}")
        print(f"CAROUSEL SEQUENTIAL GENERATION")
        print(f"{'='*60}")
        print(f"Topic: {self.topic}")
        print(f"Content slides: {len(self.slides_content)}")
        print(f"Total slides: {self.total_slides}")
        print(f"Output folder: {self.topic_folder}")
        print(f"{'='*60}")

        results = {
            "topic": self.topic,
            "folder": str(self.topic_folder),
            "success": True,
            "intro_generated": False,
            "content_generated": 0,
            "content_failed": 0,
            "cta_generated": False,
            "all_image_paths": [],
            "metadata_path": None,
        }

        # STEP 1: Generate INTRO first - this MUST succeed before proceeding
        print(f"\n{'='*60}")
        print(f"Step 1: Generating Intro Slide")
        print(f"{'='*60}")
        intro_success = self.generate_intro_slide()
        results["intro_generated"] = intro_success

        if not intro_success:
            print(f"\n[ERROR] Intro slide failed! Cannot continue without intro slide.")
            print(f"Folder: {results['folder']}")
            print(f"{'='*60}\n")
            results["success"] = False
            return results

        print(f"Intro slide generated successfully.")

        # STEP 2: Generate CONTENT slides only after intro succeeds
        print(f"\n{'='*60}")
        print(f"Step 2: Generating Content Slides")
        print(f"{'='*60}")
        content_results = self.generate_content_slides()

        successful_slides = [r for r in content_results if r["success"]]
        failed_slides = [r for r in content_results if not r["success"]]

        results["content_generated"] = len(successful_slides)
        results["content_failed"] = len(failed_slides)

        if failed_slides:
            print(f"\n[WARNING] {len(failed_slides)} content slide(s) failed:")
            for slide in failed_slides:
                print(f"  - Slide {slide['slide_number']}: {slide['heading']}")

        results["all_image_paths"].append(self.generated_images["intro"])
        results["all_image_paths"].extend(self.generated_images["content"])

        # STEP 3: Generate CTA slide only after content slides complete
        print(f"\n{'='*60}")
        print(f"Step 3: Generating CTA Slide")
        print(f"{'='*60}")
        cta_success = self.generate_cta_slide()
        results["cta_added"] = cta_success
        if cta_success and self.generated_images["cta"]:
            results["all_image_paths"].append(self.generated_images["cta"])

        metadata_path = self._save_metadata(content_results)
        results["metadata_path"] = metadata_path

        print(f"\n{'='*60}")
        print(f"GENERATION COMPLETE")
        print(f"{'='*60}")
        print(f"Intro slide: {'[OK]' if intro_success else '[FAILED]'}")
        print(f"Content slides: {len(successful_slides)}/{len(self.slides_content)} successful")
        print(f"CTA slide: {'[OK]' if cta_success else '[FAILED]'}")
        print(f"Total images: {len(results['all_image_paths'])}")
        print(f"Folder: {results['folder']}")
        print(f"{'='*60}\n")

        return results


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def generate_carousel_sequential(
    topic: str,
    slides_content: List[Dict[str, str]],
    api_key: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a carousel sequentially.

    Args:
        topic: Carousel topic/title.
        slides_content: List of dicts with 'heading' and 'description'.
        api_key: Optional Kie.ai API key.
        output_dir: Optional output directory.

    Returns:
        Dict with generated image paths and metadata.

    Example:
        >>> result = generate_carousel_sequential(
        ...     topic="AI Trends 2026",
        ...     slides_content=[
        ...         {"heading": "Introduction", "description": "AI is transforming everything."},
        ...         {"heading": "Machine Learning", "description": "ML models learn from data."},
        ...     ]
        ... )
        >>> print(f"Saved to: {result['folder']}")
    """
    generator = CarouselSequentialGenerator(
        topic=topic,
        slides_content=slides_content,
        api_key=api_key,
        output_dir=output_dir,
    )
    return generator.generate_full_carousel()


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate LinkedIn carousel slides sequentially using Kie.ai"
    )
    parser.add_argument("--topic", "-t", required=True, help="Carousel topic/title")
    parser.add_argument(
        "--slides", "-s", required=True,
        help="JSON array of slide objects: [{'heading': '...', 'description': '...'}, ...]"
    )
    parser.add_argument("--output", "-o", default=None, help="Output directory (default: carousels/)")

    args = parser.parse_args()

    try:
        slides_content = json.loads(args.slides)
    except json.JSONDecodeError as e:
        print(f"\nError: Invalid JSON for --slides: {e}")
        sys.exit(1)

    if not isinstance(slides_content, list):
        print("\nError: --slides must be a JSON array")
        sys.exit(1)

    for i, slide in enumerate(slides_content):
        if not isinstance(slide, dict) or "heading" not in slide or "description" not in slide:
            print(f"\nError: Slide {i+1} missing 'heading' or 'description' field")
            sys.exit(1)

    try:
        result = generate_carousel_sequential(
            topic=args.topic,
            slides_content=slides_content,
            output_dir=args.output,
        )
        print(f"\nCarousel saved to: {result['folder']}")

        if result["content_failed"] > 0:
            print(f"\n[WARNING] {result['content_failed']} slide(s) failed. Check logs for details.")
            sys.exit(1)

    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)