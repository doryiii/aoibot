import collections
import asyncio
from datetime import datetime
import functools
import html2text
import inspect
import json
import os
import aiohttp
from pydantic import Field


def get_time():
  """Get the current local time."""
  now = datetime.now()
  return f"{now.strftime('%A')} {now.isoformat()} {now.astimezone().tzinfo}"


async def web_fetch(url: str = Field(..., description="the webpage URL to fetch")):
  """Get content of a webpage asynchronously."""
  if not url.startswith(("http://", "https://")):
    url = "https://" + url
  async with aiohttp.ClientSession() as session:
    async with session.get(url) as resp:
      resp.raise_for_status()
      text = await resp.text()
      return html2text.html2text(text)


async def web_search(
    query: str = Field(..., description="the web search query"),
    num_results: int = Field(5, description="how many pages to get. Default 5"),
):
  """Search the web asynchronously via Langsearch API."""
  api_key = os.getenv("LANGSEARCH_API_KEY")
  if not api_key:
    raise RuntimeError("LANGSEARCH_API_KEY not set")
  payload = {"query": query, "summary": True, "count": num_results}
  headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
  async with aiohttp.ClientSession() as session:
    async with session.post("https://api.langsearch.com/v1/web-search", json=payload, headers=headers) as resp:
      resp.raise_for_status()
      res = await resp.json()
  cleaned_res = [
      {
          "name": pg.get("name"),
          "url": pg.get("url"),
          "summary": pg.get("summary") or pg.get("snippet")
      }
      for pg in res.get("data", {}).get("webPages", {}).get("value", [])
  ]
  return json.dumps(cleaned_res)


class Tools:
  TYPES = collections.defaultdict(lambda: "string", {int: "integer"})

  def __init__(self):
    self._tools = {f.__name__: f for f in [get_time, web_fetch, web_search]}

  @functools.cache
  def tools(self):
    return [self._get_spec(f) for f in self._tools.values()]

  def _get_spec(self, f):
    spec = {
        "type": "function",
        "function": {
            "name": f.__name__,
            "description": inspect.getdoc(f),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }
    for name, p in inspect.signature(f).parameters.items():
      prop = {}
      prop["type"] = self.TYPES[p.annotation]
      prop["description"] = p.default.description
      if p.default.is_required():
        spec["function"]["parameters"]["required"].append(name)
      spec["function"]["parameters"]["properties"][name] = prop
    if not spec["function"]["parameters"]["properties"]:
      spec["function"]["parameters"] = {}
    return spec

  async def call(self, method, **kwargs):
    """Dispatch a tool, awaiting if it is async."""
    if method not in self._tools:
      raise ValueError(f"unknown method: {method}")
    fn = self._tools[method]
    if asyncio.iscoroutinefunction(fn):
      return await fn(**kwargs)
    return fn(**kwargs)
