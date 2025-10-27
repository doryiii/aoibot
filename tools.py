import collections
from datetime import datetime
import functools
import html2text
import inspect
import json
import os
import requests
from pydantic import Field


def get_time():
  """Get the current local time."""
  now = datetime.now()
  return f"{now.strftime("%A")} {now.isoformat()} {now.astimezone().tzinfo}"


def web_fetch(url: str = Field(..., description="the webpage URL to fetch")):
  """Get content of a webpage."""
  if not url.startswith(("http://", "https://")):
    url = "https://" + url
  webres = requests.get(url)
  webres.raise_for_status()
  return html2text.html2text(webres.text)


def web_search(
    query: str = Field(..., description="the web search query"),
    num_results: int = Field(5, description="how many pages to get. Default 5"),
):
  """Search the web."""
  res = requests.post(
      "https://api.langsearch.com/v1/web-search",
      json={"query": query, "summary": True, "count": num_results},
      headers={
          "Content-Type": "application/json",
          "Authorization": f"Bearer {os.environ.get("LANGSEARCH_API_KEY")}",
      },
  ).json()
  cleaned_res = [
      {
          "name": pg["name"],
          "url": pg["url"],
          "summary": pg["summary"] or pg["snippet"],
      }
      for pg in res["data"]["webPages"]["value"]
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

  def call(self, method, **kwargs):
    if method not in self._tools:
      raise ValueError(f"unknown method: {method}")
    return self._tools[method](**kwargs)

