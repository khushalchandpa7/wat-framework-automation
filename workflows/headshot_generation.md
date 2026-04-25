# Headshot Generation Workflow

## Objective
Generate a professional corporate headshot from a casual user-provided photo using the Gemini Nano Banana 2 image generation model via KIE.ai.

## Required Inputs
- `input_image`: Path to the casual photo of the person (save to `headshot-input-images/`)
- `api_key`: KIE.ai API key (stored in `.env` as `KIE_API_KEY`)
- `output_filename`: Optional custom output filename (defaults to `{original_name}_headshot.png`)

## Process

1. **Validate Input**
   - Verify the input image exists and is a valid image file (JPEG, PNG)
   - Check file size is under 10MB

2. **Call KIE.ai API**
   - Use `tools/generate_headshot.py`
   - Pass the input image path and system prompt
   - Request 1K resolution output

3. **Handle Response**
   - Receive generated headshot image
   - Save to `.temp/` directory

4. **Deliver Output**
   - Move final headshot to user-accessible location or upload to cloud storage

## System Prompt (Passed to Model)
```
Primary Goal: Generate a professional headshot based on the provided reference image.

Subject & Style:
- Overall Style: A Classic Corporate headshot.
- Attire: The subject should be wearing a business suit in deep navy blue, over a white collared shirt.
- Pose: The framing is a head and shoulders shot. The subject's pose is shoulders angled slightly to the left, looking directly at the camera.
- Expression: The subject has a confident and approachable expression with a slight, natural smile.

Environment & Lighting:
- Lighting: Use a professional soft and flattering three-point studio lighting setup.
- Background: The background is a solid, neutral light-gray studio backdrop.

Technical Execution:
- Realism & Quality: The final image must be ultra-photorealistic, 8K resolution, and incredibly detailed.
- Focus & Camera: Maintain sharp focus on the eyes, creating a shallow depth of field. Emulate the look of a photo taken with a high-end DSLR camera and an 85mm f/1.4 portrait lens.
- Color & Post-Processing: Apply professional color grading and subtle, natural skin retouching.

Negative Prompts (What to Avoid):
- Avoid: cartoon, illustration, painting, distorted features, bad anatomy, extra limbs, blurry face, disfigured, deformed, unrealistic, ugly, watermark, signature. Avoid casual clothing, hats, or sunglasses.
```

## Edge Cases
- **API rate limit**: Retry after 60 seconds, max 3 retries
- **Invalid image format**: Return error with supported formats list
- **API key invalid/missing**: Return clear authentication error
- **Large file**: Compress or reject images over 10MB

## Output
- Path to generated headshot image (PNG format, 1K resolution)
- Saved to `headshot-generated-images/` directory

## Directory Structure
```
headshot-input-images/    # User uploads go here
headshot-generated-images/ # Generated headshots go here
```
