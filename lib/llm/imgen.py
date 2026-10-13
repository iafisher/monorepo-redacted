import base64
from typing import Literal

import openai

from iafisher.prelude import *
from lib import secrets


Size = Literal["auto", "square", "landscape", "portrait"]
Quality = Literal["low", "medium", "high", "xhigh", "max", "auto"]
Format = Literal["png", "jpeg", "webp"]


def generate_image(
    prompt: str,
    *,
    size: Size = "auto",
    quality: Quality = "auto",
    format_: Format = "png",
) -> bytes:
    # https://developers.openai.com/api/docs/guides/image-generation
    api_key = secrets.get_or_raise("OPENAI_API_KEY")
    client = openai.OpenAI(api_key=api_key)
    result = client.images.generate(
        model="gpt-image-2.5-sunburst",
        prompt=prompt,
        size=_size_dimensions(size),
        quality=quality,
        output_format=format_,
        moderation="low",
    )
    if not result.data:
        raise KgError(
            "The image API result is missing expected data.",
            result=result,
            prompt=prompt,
        )

    image_base64 = result.data[0].b64_json
    if image_base64 is None:
        raise KgError(
            "The image API result is missing the Base64-encoded image.",
            data=result.data[0],
            prompt=prompt,
        )

    return base64.b64decode(image_base64)


def _size_dimensions(size: Size) -> str:
    match size:
        case "auto":
            return "auto"
        case "square":
            return "1024x1024"
        case "landscape":
            return "1536x1024"
        case "portrait":
            return "1024x1536"

    impossible()
