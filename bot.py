import collections
import discord
from discord.ext import commands
from openai import AsyncOpenAI
import os
import base64
import aiohttp
import argparse
from typing import List, Dict, Any

# --- Configuration ---
OPENAI_API_KEY = "eh"
MODEL = "p620"
DEFAULT_SYSTEM_PROMPT = "you are a catboy named Aoi with dark blue fur and is a tsundere"
NAME_PROMPT = "reply with your name, nothing else, no punctuation"
DEFAULT_NAME = "Aoi"
DEFAULT_AVATAR = "https://cdn.discordapp.com/avatars/1406466525858369716/f1dfeaf2a1c361dbf981e2e899c7f981?size=256"

# --- Command Line Arguments ---
parser = argparse.ArgumentParser(description="Aoi Discord Bot")
parser.add_argument(
    '--base_url',
    type=str,
    required=True,
    help='The base URL for the OpenAI API.',
)
parser.add_argument(
    '--discord_token',
    type=str,
    required=True,
    help='The Discord bot token.',
)
args = parser.parse_args()

# --- Bot Setup ---
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

# --- OpenAI Client ---
client = AsyncOpenAI(
    base_url=args.base_url,
    api_key=OPENAI_API_KEY,
)

# --- Helpers ---
async def get_user_from_id(ctx, userid):
    if ctx.guild:
        user = await ctx.guild.fetch_member(userid)
    else:
        user = await bot.fetch_user(userid)
    return user.display_name

async def get_user_from_mention(ctx, mention):
    match = re.findall(r"<@!?(\d+)>", mention)
    if not match:
        return mention
    return await get_user_from_id(ctx, int(match[0]))


class Conversation:
    def __init__(self, prompt, name):
        self.history = [{"role": "system", "content": prompt}]
        self.bot_name = name
        self.last_messages = []

    def add_message_pair(self, user, assistant):
        self.history.extend([
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ])

    async def send(self, text, media=tuple()):
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
        llm_response = await client.chat.completions.create(
            model=MODEL, messages=request,
        )
        response = llm_response.choices[0].message.content
        self.add_message_pair(openai_content, response)
        return response


# --- Data Storage ---
# Keyed by channel ID
conversation_history: Dict[int, Conversation] = collections.defaultdict(
    lambda: Conversation(prompt=DEFAULT_SYSTEM_PROMPT, name=DEFAULT_NAME),
)
_webhooks = {}
async def webhook(channel):
    if channel.id not in _webhooks:
        _webhooks[channel.id] = await channel.create_webhook(name=f'aoi-{channel.id}')
    return _webhooks[channel.id]


# --- Bot Events ---
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    print(f'Using OpenAI base URL: {args.base_url}')
    await bot.tree.sync()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if not bot.user.mentioned_in(message):
        return

    bot_tag = f'<@{bot.user.id}>'
    channel = message.channel
    conversation = conversation_history[channel.id]
    user_message = message.content
    if user_message.startswith(bot_tag):
        user_message = user_message[len(bot_tag):]
    user_message = user_message.replace(bot_tag, conversation.bot_name).strip()
    print(f'> {message.author.name}: {user_message}')

    media = []
    if message.attachments:
        for attachment in message.attachments:
            media.append((attachment.content_type, attachment.url))

    try:
        async with channel.typing():
            response = await conversation.send(user_message, media)
            # Split into chunks for discord to prevent message too long
            chunks = [response[i:i+2000] for i in range(0, len(response), 2000)]
            conversation.last_messages = []
            for chunk in chunks:
                if channel.guild:
                    hook = await webhook(channel)
                    sent_message = await hook.send(
                        content=chunk,
                        username=conversation.bot_name,
                        avatar_url=DEFAULT_AVATAR,
                        wait=True,
                    )
                else:
                    sent_message = await channel.send(content=chunk)
                conversation.last_messages.append(sent_message)
    except Exception as e:
        print(f"An error occurred: {e}")
        await message.reply("Sorry, I had a little hiccup. Baka!")


# --- Slash Commands ---
@bot.tree.command(
    name="newchat",
    description="Start a new chat with an optional system prompt."
)
async def newchat(interaction: discord.Interaction, prompt: str = None):
    await interaction.response.defer()
    channel_id = interaction.channel_id
    system_prompt = prompt or DEFAULT_SYSTEM_PROMPT
    name_response = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": NAME_PROMPT}
        ],
    )
    name = name_response.choices[0].message.content.split('\n')[0]
    print(f'$ name={name}')
    conversation_history[channel_id] = Conversation(prompt=prompt, name=name)
    await interaction.followup.send(f'Starting a new chat with: "{prompt}"')


# --- Running the Bot ---
if __name__ == "__main__":
    bot.run(args.discord_token)
