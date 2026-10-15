from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)

messages = [
    {
        "role": "system",
        "content": "You are a helpful academic mentor."
    }
]

while True:
    user_input = input("User: ")

    if user_input.lower() in ["exit", "quit"]:
        break

    messages.append({
        "role": "user",
        "content": user_input
    })

    response = client.chat.completions.create(
        model="qwen2.5:1.5b",
        messages=messages
    )

    assistant_reply = response.choices[0].message.content

    print("Assistant:", assistant_reply)

    messages.append({
        "role": "assistant",
        "content": assistant_reply
    })