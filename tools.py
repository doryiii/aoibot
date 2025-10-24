from abc import ABC, abstractmethod
from datetime import datetime
import functools
import html2text
import json
import os
import requests


class Tool(ABC):
    @abstractmethod
    def get_spec(self):
        """Returns the dictionary representing function spec for the tool."""
        ...

    @abstractmethod
    def run(self, **kwargs):
        """Executes the tool with the required parameters."""
        ...



class Time(Tool):
    def get_spec(self):
      return {
          "type": "function",
          "function": {
              "name": "get_time",
              "description": "Get the current local time.",
              "parameters": {},
          },
      }

    def run(self):
        now = datetime.now()
        return f"{now.isoformat()} {now.astimezone().tzinfo}"


class WebFetch(Tool):
    def get_spec(self):
        return {
            "type": "function",
            "function": {
                "name": "web_fetch",
                "description": "Get content of a webpage.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "the webpage URL to fetch"
                        }
                    },
                    "required": ["url"],
                },
            },
        }

    def run(self, url):
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        webres = requests.get(url)
        webres.raise_for_status()
        return html2text.html2text(webres.text)


class WebSearch(Tool):
    def get_spec(self):
        return {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "the web search query"
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "how many sites to return. Default is 5"
                        }
                    },
                    "required": ["query"],
                },
            },
        }

    def run(self, query, num_results=5):
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
    def __init__(self):
        tools = [cls() for cls in Tool.__subclasses__()]
        self._tools = {t.get_spec()["function"]["name"]: t for t in tools}

    @functools.cache
    def tools(self):
        return [tool.get_spec() for tool in self._tools.values()]

    def call(self, method, **kwargs):
        if method not in self._tools:
            raise ValueError(f"unknown method: {method}")
        return self._tools[method].run(**kwargs)
