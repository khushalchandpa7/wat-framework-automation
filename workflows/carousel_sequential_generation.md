# Carousel Sequential Generation Workflow

## Objective

Generate a complete LinkedIn carousel with an intro slide, followed by content slides generated one-by-one sequentially, and save all images to a `carousels/{topic_name}/` folder.

This workflow uses the WAT (Workflows, Agents, Tools) architecture:
- **Workflow**: This document defines the process
- **Agent**: You (the decision-maker who orchestrates the flow)
- **Tool**: `tools/carousel_sequential.py` handles deterministic execution

## Required Inputs

| Input | Type | Description | Example |
|-------|------|-------------|---------|
| `topic` | string | Carousel topic/title | "AI Trends 2026" |
| `slides_content` | list[dict] | List of slide content with heading + description | See below |

### Slides Content Structure

```python
[
    {"heading": "Introduction to AI", "description": "AI is transforming how we work and live."},
    {"heading": "Machine Learning", "description": "ML models learn from data to make predictions."},
    {"heading": "Neural Networks", "description": "Deep learning powers modern AI applications."},
]
```

## Expected Output

### Folder Structure

```
carousels/
└── {topic_name}_{timestamp}/
    ├── 0_intro.png          # Intro slide (generated via Kie.ai)
    ├── 1_content.png        # Content slide 1 (generated via Kie.ai)
    ├── 2_content.png        # Content slide 2 (generated via Kie.ai)
    ├── 3_content.png        # Content slide 3 (generated via Kie.ai)
    ├── N_cta.png            # CTA slide (generated via Kie.ai, N = total content slides)
    └── carousel_metadata.json # Metadata with all image paths
```

### Output Metadata (carousel_metadata.json)

```json
{
    "topic": "AI Trends 2026",
    "folder": "carousels/ai_trends_2026_20260423_143022",
    "intro_slide": "carousels/.../0_intro.png",
    "content_slides": [
        {"path": "carousels/.../1_content.png", "heading": "Intro to AI", "success": true},
        {"path": "carousels/.../2_content.png", "heading": "Machine Learning", "success": true},
        {"path": "carousels/.../3_content.png", "heading": "Neural Networks", "success": true}
    ],
    "cta_slide": "carousels/.../3_cta.png",
    "all_slides": [
        "carousels/.../0_intro.png",
        "carousels/.../1_content.png",
        "carousels/.../2_content.png",
        "carousels/.../3_content.png",
        "carousels/.../3_cta.png"
    ],
    "total_slides": 5,
    "generated_at": "2026-04-23T14:30:22"
}
```

## Usage

### Method 1: Python Module

```python
from tools.carousel_sequential import generate_carousel_sequential

result = generate_carousel_sequential(
    topic="AI Trends 2026",
    slides_content=[
        {"heading": "Introduction to AI", "description": "AI is transforming how we work."},
        {"heading": "Machine Learning", "description": "ML models learn from data."},
        {"heading": "Neural Networks", "description": "Deep learning powers AI."},
    ]
)

print(f"Carousel saved to: {result['folder']}")
```

### Method 2: Command Line

```bash
cd D:\Claude Code
python tools/carousel_sequential.py \
    --topic "AI Trends 2026" \
    --slides '[{"heading": "Intro", "description": "Description 1"}, {"heading": "ML", "description": "Description 2"}]'
```

## Generation Process

The tool generates slides in this exact sequence:

1. **Intro Slide** → `0_intro.png`
   - Uses Kie.ai image-to-image with template
   - Replaces `[CONTENT HEADING]` with topic
   - Replaces `[N]` with total slide count

2. **Content Slide 1** → `1_content.png`
   - Uses Kie.ai image-to-image with template
   - Replaces `0[N]` with `01`
   - Replaces heading/description with slide 1 content

3. **Content Slide 2** → `2_content.png`
   - Same process, slide number `2`

4. **Content Slide N** → `N_content.png`
   - Continues for all slides in sequence

5. **CTA Slide** → `N_cta.png`
   - Generated from CTA template using Kie.ai
   - Slide number equals total content slides

6. **Save Metadata** → `carousel_metadata.json`
   - Records all paths and metadata

## Kie.ai API Configuration

### Templates
- **Intro**: `https://i.ibb.co/mrpfz00G/carousel-intro-slide-template.png`
- **Content**: `https://i.ibb.co/MDnv28r9/carousel-content-slide-template.png`
- **CTA**: `https://i.ibb.co/nqSdc1RY/carousel-cta-slide.png`

### Model
- Model: `gpt-image-2-image-to-image`
- Aspect ratio: `1:1`

### Polling Configuration
- Poll interval: 15 seconds
- Max retries: 240 attempts
- Backoff multiplier: 1.0x

## Error Handling

### API Rate Limits
- **Symptom**: HTTP 429 response → `RateLimitError`
- **Handling**: Automatic retry with backoff
- If persistent, wait and retry manually

### Generation Failures
- **Symptom**: Task state = "fail" → `GenerationError`
- **Handling**:
  1. Log error with task ID and slide number
  2. Continue with remaining slides (don't abort entire carousel)
  3. Report partial success in final metadata

### Partial Generation Success
- If some slides fail, the tool:
  1. Saves successfully generated slides to folder
  2. Records failed slides in metadata with `"success": false`
  3. Returns partial result so user can retry failed slides

## Related Files

| File | Purpose |
|------|---------|
| `tools/carousel_sequential.py` | Main sequential generator |
| `tools/kie_api.py` | Shared Kie.ai API wrapper |
| `carousel-starting-images/` | Reference slides for style |
| `carousels/` | Output folder for generated carousels |

## Success Criteria

- [ ] Intro slide generated with correct topic and slide count
- [ ] All content slides generated in sequential order
- [ ] Each content slide has correct slide number (1, 2, 3...)
- [ ] All images saved to `carousels/{topic}_{timestamp}/` folder
- [ ] Metadata JSON file created with all paths
- [ ] 5 second delay between slides to avoid API throttling