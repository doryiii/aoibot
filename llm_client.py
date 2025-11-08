import aiohttp
import json


class LLMClient:
  def __init__(self, base_url, model, api_key="eh", backup_url=None):
    self.base_url = base_url
    self.model = model
    self.api_key = api_key
    self.backup_url = backup_url

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

    async with aiohttp.ClientSession(
        raise_for_status=True, headers=headers,
    ) as session:
      try:
        async with session.post(
            f"{self.base_url}/chat/completions", data=json.dumps(payload),
        ) as response:
          return await response.json()

      except (aiohttp.ClientConnectorError, aiohttp.ClientResponseError) as e:
        if not self.backup_url:
          raise e
        async with session.post(
            f"{self.backup_url}/chat/completions", data=json.dumps(payload),
        ) as response:
          return await response.json()
