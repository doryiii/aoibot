import aiohttp
import base64
import json

from llm_client import LLMClient
from tools import Tools

DEFAULT_NAME = "Aoi"
NAME_PROMPT = "reply with your name, nothing else, no punctuation"


async def get_name(client: LLMClient, prompt):
  """Generates an assistant name for the given prompt."""
  name_response = await client.chat(
      messages=[
          {"role": "system", "content": prompt},
          {"role": "user", "content": NAME_PROMPT}
      ],
  )
  return name_response['choices'][0]['message']['content'].split('\n')[0]


class ConversationManager:
  """Creates and retrieves Conversations."""

  def __init__(self, llm_client, db, default_prompt):
    self.client = llm_client
    self.db = db
    self.default_prompt = default_prompt

  async def get(self, key, create_if_missing=True):
    """Gets a conversation based on |key|, optionally create when not found."""
    convo_data = self.db.get_conversation(key)
    if convo_data:
      prompt, web_access, history, bot_name, last_messages = convo_data
      return Conversation(
          key, bot_name, prompt, web_access, history, last_messages,
          self.client, self.db,
      )
    if create_if_missing:
      return await self.new_conversation(key, self.default_prompt)
    return None

  async def new_conversation(self, key, prompt=None, web_access=False):
    """Creates a new Conversation with key based on given prompt."""
    prompt = prompt or self.default_prompt
    name = await get_name(self.client, prompt)
    history = []
    last_messages = []
    convo = Conversation(
        key, name, prompt, web_access, history, last_messages,
        self.client, self.db,
    )
    await convo.save()
    return convo


class Conversation:
  """Holds data about a conversation thread."""

  def __init__(
      self,
      convo_id, name, prompt, web_access,
      history, last_messages,
      api_client, db,
  ):
    self.id = convo_id
    self.bot_name = name
    self.prompt = prompt
    self.web_access = web_access
    self.history = history
    self.last_messages = last_messages
    self.client = api_client
    self.db = db
    self.tools = Tools()

  async def save(self):
    """Saves the conversation to the DB."""
    self.db.save(
        self.id, self.prompt, self.web_access,
        self.history, self.bot_name, self.last_messages
    )

  async def pop(self):
    """Removes the last user turn and all subsequent assistant turns."""
    while self.history:
      current = self.history.pop()
      if current["role"] == "user":
        await self.save()
        return current
    await self.save()
    return None

  async def update_prompt(self, prompt, web_access=None):
    """Changes current prompt to a new one, keeping the rest of history."""
    self.prompt = prompt
    self.bot_name = await get_name(self.client, prompt)
    if web_access is not None:
      self.web_access = web_access
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
    user_turn = {"role": "user", "content": openai_content}
    return await self._generate([user_turn])

  async def _generate(self, user_turns):
    to_sends = [user_turns]
    while to_sends:
      to_send = to_sends.pop(0)
      request = (
          [{"role": "system", "content": self.prompt}]
          + self.history + to_send
      )
      llm_response = await self.client.chat(
          messages=request,
          tools=self.tools.tools() if self.web_access else None,
          stream=False, extra_body={"cache_prompt": True},
      )
      llm_response = llm_response['choices'][0]['message']
      self.history.extend(to_send)
      self.history.append({k: v for k, v in llm_response.items() if v})

      # check for tool calls
      if 'tool_calls' in llm_response and llm_response['tool_calls']:
        tool_results = []
        for tool_call in llm_response['tool_calls']:
          print(f"calling {tool_call['function']}... ")
          tool_result_text = self.tools.call(
              tool_call['function']['name'],
              **json.loads(tool_call['function']['arguments'])
          )
          tool_results.append({
              "role": "tool",
              "tool_call_id": tool_call['id'],
              "content": tool_result_text,
          })
        to_sends.append(tool_results)
    return llm_response['content']

  async def regenerate(self):
    """Regenerates the last assistant turn."""
    last_user_turn = await self.pop()
    return await self._generate([last_user_turn])
