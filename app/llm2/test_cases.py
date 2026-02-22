from iafisher_foundation.prelude import *
from lib import llm


class WeatherTool(llm.BaseTool):
    @override
    @classmethod
    def get_name(cls) -> str:
        return "get_weather"

    @override
    @classmethod
    def get_plain_description(cls) -> str:
        return "Get the current weather in a given location"

    @override
    @classmethod
    def get_input_schema(cls) -> StrDict:
        return dict(
            type="object",
            properties=dict(
                location=dict(
                    type="string",
                    description="The city and state, e.g. San Francisco, CA",
                ),
            ),
            required=["location"],
        )

    @override
    @classmethod
    def get_output_schema(cls) -> StrDict:
        return dict(type="string", description="A description of the current weather")

    @override
    def call(self, params: Any) -> Any:
        location = params["location"]
        if "Fargo" in location:
            raise Exception("North Dakota is not in the weather database.")
        return f"It's a balmy 70 degrees Fahrenheit in {location}."


# TODO(2026-01): Reimplement some test cases.
