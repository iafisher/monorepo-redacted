from iafisher_foundation.prelude import *
from lib import llm, pdb


SYSTEM_PROMPT = """\
You are a proofreader LLM. You should read the text and flag the following issues:

- Typos
- Grammatical errors
- Factual mistakes, based on your knowledge about the world

You are prompted with the text to proofread. Assume it is in Markdown format. You
are typically invoked non-interactively.
"""


def main(filepath: pathlib.Path, *, model: str = llm.ANY_MODEL) -> None:
    text_to_proofread = filepath.read_text()
    with pdb.connect() as db:
        model_response = llm.oneshot(
            db,
            text_to_proofread,
            model=model,
            system_prompt=SYSTEM_PROMPT,
            app_name="llm2::proofread",
            options=llm.InferenceOptions.normal(),
            hooks=llm.PrintTextHook(),
        )
        print()
        print(f"Conversation ID: {model_response.conversation_id}")
