import os

os.environ["JSON_LOGS"] = "true"
import litellm  # noqa: E402
from lib import secrets  # noqa: E402


litellm._turn_on_debug()  # type: ignore
api_key = secrets.get_or_raise("ANTHROPIC_API_KEY")
messages = [{"content": "What is the capital of Libya?", "role": "user"}]
response = litellm.completion(  # type: ignore
    model="anthropic/claude-haiku-4-5-20251001",
    messages=messages,
    api_key=api_key,
)
print(response)
