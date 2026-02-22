import pickle

from iafisher_foundation.prelude import *
from lib import command, kgenv, llm, pdb


def main_record(
    *, model: str, prompt: str, outfile: pathlib.Path, web_search: bool
) -> None:
    with pdb.connect() as db:
        conversation = llm.Conversation.start(
            db, model=model, app_name="llm2::trace", system_prompt=""
        )

        hooks = llm.BaseHooks()
        options = llm.InferenceOptions.normal()
        tools: List[llm.BaseTool] = []

        if web_search:
            tools.append(llm.tools.WebSearchTool())

        response1 = conversation.prompt(
            db, prompt, hooks=hooks, options=options, tools=tools, trace=True
        )

        with open(outfile, "wb") as f:
            pickle.dump(response1.trace, f)


def main_replay(name: str) -> None:
    with open(
        kgenv.get_code_dir() / "lib" / "llm" / "mocks" / f"{name}.pkl", "rb"
    ) as f:
        data = pickle.load(f)

    for turn in data["turns"]:
        for message in turn["stream"]:
            print()
            print()
            print()
            print(message)


cmd = command.Group(help="Trace raw API responses.")
cmd.add2("record", main_record)
cmd.add2("replay", main_replay)
