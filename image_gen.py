import os
import requests
from io import BytesIO
from PIL import Image
import openai


# Newsletter header dimensions — wide enough for email, small enough for fast loading
_TARGET_W = 640
_TARGET_H = 320


def generate_header_image(image_prompt: str) -> bytes:
    """Generate a header image for the newsletter and return resized JPEG bytes."""
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    response = client.images.generate(
        model="dall-e-3",
        prompt=image_prompt,
        size="1792x1024",
        quality="standard",
        n=1,
    )

    url = response.data[0].url
    raw = requests.get(url, timeout=30).content

    img = Image.open(BytesIO(raw)).convert("RGB")
    img = img.resize((_TARGET_W, _TARGET_H), Image.LANCZOS)

    out = BytesIO()
    img.save(out, format="JPEG", quality=82)
    return out.getvalue()
