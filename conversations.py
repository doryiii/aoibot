import aiohttp
import base64
import re
from database import Database
from url_to_llm_text.get_llm_ready_text import url_to_llm_text

API_KEY = "eh"
MODEL = "p620"
DEFAULT_NAME = "Aoi"
NAME_PROMPT = "reply with your name, nothing else, no punctuation"
WEB_FETCH_PROMPT_PART = (
    "You have access to the internet. If you decide to look at website(s), "
    "you MUST put it in the format [web_fetch(url=\"https://web.site.link.1\"),"
    " web_fetch(url=\"https://web.site.link.2\")] \n\n"
    "You SHOULD NOT include any other text in the response if you want to "
    "look at websites."
)
WEB_FETCH_RE = re.compile(r'(web_fetch\(url="(?P<url>[^"]+)"\))+')

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
            history, bot_name, last_messages = convo_data
            return Conversation(
                key, bot_name, history, last_messages,
                self.client, self.model, self.db,
            )
        if create_if_missing:
            return await self.new_conversation(key, self.default_prompt)
        return None

    async def new_conversation(self, key, prompt = None, web_fetch = True):
        """Creates a new Conversation with key based on given prompt."""
        prompt = prompt or self.default_prompt
        if web_fetch:
            full_prompt = prompt + "\n\n" + WEB_FETCH_PROMPT_PART
        else:
            full_prompt = prompt
        name = await get_name(self.client, self.model, prompt)
        history = [{"role": "system", "content": full_prompt}]
        last_messages = []
        convo = Conversation(
            key, name, history, last_messages, self.client, self.model, self.db,
        )
        await convo.save()
        return convo


class Conversation:
    """Holds data about a conversation thread."""
    def __init__(
        self,
        convo_id, name,
        history, last_messages,
        api_client, model, db,
    ):
        self.id = convo_id
        self.bot_name = name
        self.history = history
        self.last_messages = last_messages
        self.client = api_client
        self.model = model
        self.db = db

    async def save(self):
        """Saves the conversation to the DB."""
        self.db.save(self.id, self.history, self.bot_name, self.last_messages)

    def add_message_pair(self, user, assistant):
        """Adds a user/assistant convesation turn pair."""
        self.history.extend([
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ])

    async def pop(self):
        """Removes one user/assistant converation turn pair."""
        if len(self.history) >= 3:
            self.history = self.history[:-2]
            await self.save()

    async def update_prompt(self, prompt, web_fetch):
        """Changes current prompt to a new one, keeping the rest of history."""
        if web_fetch:
            full_prompt = prompt + "\n\n" + WEB_FETCH_PROMPT_PART
        else:
            full_prompt = prompt
        self.history[0] = {"role": "system", "content": full_prompt}
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
        to_send = openai_content
        while to_send:
            request = self.history + [{"role": "user", "content": to_send}]
            llm_response = await self.client.chat.completions.create(
                model=MODEL, messages=request,
            )
            resp = llm_response.choices[0].message.content.strip()
            self.add_message_pair(openai_content, resp)
            # check for web requests
            urls = [m.group("url") for m in WEB_FETCH_RE.finditer(resp)]
            if not resp.startswith("[") or not resp.endswith("]") or not urls:
                break
            print(f"{self.id}? {urls}")
            fetches = [f"{u}:\n\n{(await url_to_llm_text(u))}" for u in urls]
            to_send = [{"type": "text", "text": "\n\n".join(fetches)}]

        return resp

    async def regenerate(self):
        """Regenerates the last assistant turn."""
        llm_response = await self.client.chat.completions.create(
            model=MODEL, messages=self.history[:-1]
        )
        response = llm_response.choices[0].message.content
        self.history[-1] = {"role": "assistant", "content": response}
        return response
