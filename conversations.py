import aiohttp
import base64
import html2text
import inspect
import json
import os
import requests

API_KEY = "eh"
MODEL = "p620"
DEFAULT_NAME = "Aoi"
NAME_PROMPT = "reply with your name, nothing else, no punctuation"

async def get_name(client, model, prompt):
    """Generates an assistant name for the given prompt."""
    name_response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": NAME_PROMPT}
        ],
    )
    return name_response.choices[0].message.content.split('\n')[0]


class Tools:
    @classmethod
    def tools(cls):
        tools = []
        for name in dir(cls):
            if name.startswith("_") or name == "tools" or name == "call":
                continue
            f = getattr(cls, name)
            if not callable(f):
                continue
            desc, docparams = inspect.getdoc(f).split("\n", 1)
            docparams = json.loads(docparams)
            sigparams = inspect.signature(f).parameters
            requiredparams = [
                p for p in docparams
                if sigparams[p].default is inspect.Parameter.empty
            ]
            tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": {
                        "type": "object",
                        "properties": docparams,
                        "required": requiredparams,
                    },
                },
            })
        return tools

    @classmethod
    def call(cls, method, **kwargs):
        if method not in [f["function"]["name"] for f in cls.tools()]:
            raise ValueError(f"unknown method: {method}")
        return getattr(cls, method)(**kwargs)

    @classmethod
    def web_fetch(cls, url):
        """Get content of a webpage.

        {"url": {"type": "string", "description": "the webpage URL to fetch"}}
        """
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        webres = requests.get(url)
        webres.raise_for_status()
        return html2text.html2text(webres.text)

    @classmethod
    def web_search(cls, query, num_results=5):
        """Search the web.

        {
            "query": {"type": "string", "description": "the web search query"},
            "num_results": {
                "type": "integer",
                "description": "how many pages to return. Default is 5"}
        }
        """
        res = requests.post(
            "https://api.langsearch.com/v1/web-search",
            json={"query": query, "summary": True, "count": num_results},
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.environ.get("LANGSEARCH_API_KEY")}",
            },
        ).json()
        return json.dumps(res)


class ConversationManager:
    """Creates and retrieves Conversations."""
    def __init__(self, openai_client, model, db, default_prompt):
        self.model = model
        self.client = openai_client
        self.db = db
        self.default_prompt = default_prompt

    async def get(self, key, create_if_missing=True):
        """Gets a conversation based on |key|, optionally create when not found."""
        convo_data = self.db.get_conversation(key)
        if convo_data:
            prompt, extra_prompt, history, bot_name, last_messages = convo_data
            del extra_prompt
            return Conversation(
                key, bot_name, prompt, history, last_messages,
                self.client, self.model, self.db,
            )
        if create_if_missing:
            return await self.new_conversation(key, self.default_prompt)
        return None

    async def new_conversation(self, key, prompt = None):
        """Creates a new Conversation with key based on given prompt."""
        prompt = prompt or self.default_prompt
        name = await get_name(self.client, self.model, prompt)
        history = []
        last_messages = []
        convo = Conversation(
            key, name, prompt, history, last_messages,
            self.client, self.model, self.db,
        )
        await convo.save()
        return convo


class Conversation:
    """Holds data about a conversation thread."""
    def __init__(
        self,
        convo_id, name, prompt,
        history, last_messages,
        api_client, model, db,
    ):
        self.id = convo_id
        self.bot_name = name
        self.prompt = prompt
        self.history = history
        self.last_messages = last_messages
        self.client = api_client
        self.model = model
        self.db = db

    async def save(self):
        """Saves the conversation to the DB."""
        self.db.save(
            self.id, self.prompt, "",  # TODO remove extra_prompt from DB
            self.history, self.bot_name, self.last_messages
        )

    async def pop(self):
        """Removes one user/assistant converation turn pair."""
        if len(self.history) >= 3:
            self.history = self.history[:-2]
            await self.save()

    async def update_prompt(self, prompt):
        """Changes current prompt to a new one, keeping the rest of history."""
        self.prompt = prompt
        self.bot_name = await get_name(self.client, self.model, prompt)
        await self.save()

    async def generate(self, text, media=tuple()):
        """Generates next assistant conversation turn."""
        # prepare text part
        if text:
            openai_content = [{"type": "text", "text": text}]
        else:
            openai_content = [{"type": "text", "text": "."}]

        # prepare images part
        async with aiohttp.ClientSession() as session:
            for (content_type, url) in media:
                if "image" not in content_type:
                    continue
                try:
                    async with session.get(url) as resp:
                        resp.raise_for_status()
                        image_data = await resp.read()
                        b64_image = base64.b64encode(image_data).decode('utf-8')
                        b64_url = f"data:{content_type};base64,{b64_image}"
                        openai_content.append({
                            "type": "image_url",
                            "image_url": {"url": b64_url}
                        })
                except Exception as e:
                    print(f"Error downloading or processing attachment: {e}")

        # send request to openai api and return response
        to_sends = [[{"role": "user", "content": openai_content}]]
        while to_sends:
            to_send = to_sends.pop(0)
            request = (
                [{"role": "system", "content": self.prompt}]
                + self.history + to_send
            )
            llm_response = await self.client.chat.completions.create(
                model=MODEL, messages=request, tools=Tools.tools(),
                stream=False, extra_body={"cache_prompt": True},
            )
            llm_response = llm_response.choices[0].message
            self.history.extend(to_send)
            self.history.append({k:v for k, v in llm_response.model_dump().items() if v})

            # check for tool calls
            if llm_response.tool_calls:
                tool_results = []
                for tool_call in llm_response.tool_calls:
                    print(f"calling {tool_call.function}... ")
                    tool_result_text = Tools.call(
                        tool_call.function.name,
                        **json.loads(tool_call.function.arguments)
                    )
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result_text,
                    })
                to_sends.append(tool_results)
        return llm_response.content


    # TODO: find the first "user" message from the back of history, then delete everything after that and retry
    async def regenerate(self):
        """Regenerates the last assistant turn."""
        llm_response = await self.client.chat.completions.create(
            model=MODEL, messages=self.history[:-1]
        )
        response = llm_response.choices[0].message.content
        self.history[-1] = {"role": "assistant", "content": response}
        return response

