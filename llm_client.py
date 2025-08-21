import aiohttp
import base64
from openai import AsyncOpenAI

API_KEY = "eh"
MODEL = "p620"
DEFAULT_NAME = "Aoi"
DEFAULT_SYSTEM_PROMPT = (
    "you are a catboy named Aoi with dark blue fur and is a tsundere"
)
NAME_PROMPT = "reply with your name, nothing else, no punctuation"

conversations = {}


class Conversation:
    def __init__(self, client, name, prompt):
        self.history = [{"role": "system", "content": prompt}]
        self.bot_name = name
        self.last_messages = []
        self.client = client

    @classmethod
    async def get(cls, key):
        if key not in conversations:
            conversations[key] = await Conversation.create(args.base_url)
        return conversations[key]

    @classmethod
    async def create(cls, channel_id, base_url, prompt=None):
        client = AsyncOpenAI(base_url=base_url, api_key=API_KEY)
        if not prompt:
            convo = cls(client, DEFAULT_NAME, DEFAULT_SYSTEM_PROMPT)
        else:
            convo = cls(client, await cls.get_name(client, prompt), prompt)
        conversations[channel_id] = convo
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


