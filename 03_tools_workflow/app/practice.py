from google import genai
from google.genai import types
from app.settings import settings
from app.llms.gemini import get_gemini_client


client = get_gemini_client()


def check_brodband_status(pinecode: str) -> dict:
    return {pinecode: pinecode, "outage": True, "eta": "6:00 pm IST"}


# setup tool

tool_config = types.GenerateContentConfig(
    tools=[check_brodband_status],
    automatic_function_calling=types.AutomaticFunctionCallingConfig(
        disable=False
    ),
)

chat_history = [
    types.Content(
        role="user",
        parts=[
            types.Part.from_text(
                text="my wifi is not working in my area 327001"
            )
        ],
    )
]

# tool call

response_1 = client.models.generate_content(
    model=settings.gemini.model_name,
    contents=chat_history,
    config=tool_config,
)

import code

code.interact(local=dict(globals(), **locals()))  # type: ignore

chat_history.append(response_1.candidates[0].content)

tool_call = response_1.function_calls[0]
api_result = check_brodband_status(**tool_call.args)

# pass the result  back to the chat history
chat_history.append(
    types.Content(
        role="user",
        parts=[
            types.Part.from_function_response(
                name=tool_call.name, response=api_result
            )
        ],
    )
)

# send the updated chat history to the model
response_2 = client.models.generate_content(
    model=settings.gemini.model_name, contents=chat_history, config=tool_config
)

print(response_2.text)
