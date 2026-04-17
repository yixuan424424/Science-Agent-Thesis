"""验证 LLM API 连通性。"""

from src.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from openai import OpenAI

print(f"Base URL: {LLM_BASE_URL}")
print(f"Model:    {LLM_MODEL}")
print(f"API Key:  {LLM_API_KEY[:8]}...{LLM_API_KEY[-4:]}")
print("-" * 40)

client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

response = client.chat.completions.create(
    model=LLM_MODEL,
    messages=[{"role": "user", "content": "Calculate 1+1 and reply with just the number."}],
    max_tokens=10,
)

print(f"Response: {response.choices[0].message.content}")
print(f"Tokens:   {response.usage.prompt_tokens} prompt + {response.usage.completion_tokens} completion")
print("\nAPI verification passed!")
