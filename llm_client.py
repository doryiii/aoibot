import aiohttp
import base64
from openai import AsyncOpenAI
from database import Database

API_KEY = "eh"
MODEL = "p620"
DEFAULT_NAME = "Aoi"
DEFAULT_SYSTEM_PROMPT = (
    "you are a catboy named Aoi with dark blue fur and is a tsundere"
)
NAME_PROMPT = "reply with your name, nothing else, no punctuation"


class Conversation:
    def __init__(self, client, name, prompt, convo_id, db):
        self.history = [{"role": "system", "content": prompt}]
        self.bot_name = name
        self.last_messages = []
        self.client = client
        self.id = convo_id
        self.db = db

    def __str__(self):
        return (
            f"Conversation({self.bot_name}, {self.last_messages}, "
            f"{self.history}"
        )

    async def save(self):
        self.db.save(
            self.id, self.history, self.bot_name, self.last_messages
        )

    @classmethod
    async def get(cls, key, base_url, db):
        convo_data = db.get_conversation(key)
        if convo_data:
            history, bot_name, last_messages = convo_data
            client = AsyncOpenAI(base_url=base_url, api_key=API_KEY)
            convo = cls(client, bot_name, history[0]['content'], key, db)
            convo.history = history
            convo.last_messages = last_messages
            return convo
        return await Conversation.create(key, base_url, db)

    @classmethod
    async def create(cls, key, base_url, db, prompt=None):
        client = AsyncOpenAI(base_url=base_url, api_key=API_KEY)
        if not prompt:
            convo = cls(client, DEFAULT_NAME, DEFAULT_SYSTEM_PROMPT, key, db)
        else:
            name = await cls.get_name(client, prompt)
            convo = cls(client, name, prompt, key, db)
        await convo.save()
        return convo

    @classmethod
    async def get_name(self, client, system_prompt):
        name_response = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": NAME_PROMPT}
            ],
        )
        return name_response.choices[0].message.content.split('\n')[0]

    def add_message_pair(self, user, assistant):
        self.history.extend([
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ])

    async def pop(self):
        if len(self.history) >= 3:
            self.history = self.history[:-2]
            await self.save()

    async def update_prompt(self, prompt):
        self.history[0] = {"role": "system", "content": prompt}
        self.bot_name = await self.get_name(self.client, prompt)
        await self.save()

    async def generate(self, text, media=tuple()):
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
                        if resp.status != 200:
                            raise IOError(f"{url} --> {resp.status}")
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
        request = self.history + [{"role": "user", "content": openai_content}]
        llm_response = await self.client.chat.completions.create(
            model=MODEL, messages=request,
        )
        response = llm_response.choices[0].message.content
        self.add_message_pair(openai_content, response)
        return response

    async def regenerate(self):
        llm_response = await self.client.chat.completions.create(
            model=MODEL, messages=self.history[:-1]
        )
        response = llm_response.choices[0].message.content
        self.history[-1] = {"role": "assistant", "content": response}
        return response

