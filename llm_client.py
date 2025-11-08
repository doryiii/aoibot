import aiohttp
import json


class LLMClient:
  def __init__(self, base_url, model, api_key="eh"):
    self.base_url = base_url
    self.model = model
    self.api_key = api_key

  async def chat(self, messages, tools=None, extra_body=None):
    """Makes a chat completion request to the LLM server."""
    payload = {
        "model": self.model,
        "messages": messages,
        "stream": False,
    }
    if tools:
      payload["tools"] = tools
    if extra_body:
      payload.update(extra_body)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {self.api_key}",
    }

    async with aiohttp.ClientSession() as session:
      async with session.post(
          f"{self.base_url}/chat/completions",
          headers=headers,
          data=json.dumps(payload),
      ) as response:
        response.raise_for_status()
        return await response.json()
