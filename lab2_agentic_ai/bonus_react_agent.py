from dotenv import load_dotenv
from google import genai
from google.genai import types
import json

load_dotenv()
client = genai.Client()

from module3_tools import lookup_cve_details


def get_installed_packages(hostname: str) -> list[str]:
    mock_hosts = {
        "db-prod-01": [
            "openssh-server 9.6",
            "xz-utils 5.6.1",
            "postgresql 16"
        ]
    }

    return mock_hosts.get(hostname, [])


def run_react_agent(user_prompt: str, max_iterations: int = 5):
    tools_map = {
        "lookup_cve_details": lookup_cve_details,
        "get_installed_packages": get_installed_packages
    }

    config = types.GenerateContentConfig(
        system_instruction=(
            "You are a cybersecurity assistant. "
            "Use the available tools to verify CVE information and installed packages. "
            "Do not invent vulnerability details or package versions. "
            "After gathering the necessary information, provide a clear security assessment."
        ),
        tools=[lookup_cve_details, get_installed_packages],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(
            disable=True
        ),
        temperature=0.0,
    )
    messages = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_prompt)]
        )
    ]

    for iteration in range(max_iterations):
        print(f"\n[Iteration {iteration + 1}]")

        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=messages,
            config=config,
        )

        tool_calls = response.function_calls or []

        if not tool_calls:
            print("\n[Final Agent Answer]")
            print(response.text)
            return response.text
        
        messages.append(response.candidates[0].content)

        tool_response_parts = []

        for tool_call in tool_calls:
            print(f"\n[Tool Requested] {tool_call.name}")
            print(f"[Arguments] {tool_call.args}")

            if tool_call.name not in tools_map:
                tool_result = {"error": "Unknown tool"}
            else:
                tool_function = tools_map[tool_call.name]
                tool_result = tool_function(**tool_call.args)

            print(f"[Tool Result] {tool_result}")

            tool_response_parts.append(
                types.Part.from_function_response(
                    name=tool_call.name,
                    response={"result": tool_result}
                )
            )

        messages.append(
            types.Content(
                role="user",
                parts=tool_response_parts
            )
        )

    print("\n[STOP] Maximum number of iterations reached.")
    return None

if __name__ == "__main__":
    run_react_agent(
        "Check whether the server db-prod-01 is vulnerable to CVE-2024-3094. "
        "Use the available tools to verify the vulnerability and installed packages."
    )