import discord
from discord.ext import commands
from openai import AsyncOpenAI
import os
import base64
import aiohttp
import argparse
from dataclasses import dataclass, field
from typing import List, Dict, Any

# --- Configuration ---
OPENAI_API_KEY = "eh"
DEFAULT_SYSTEM_PROMPT = "you are a catboy named Aoi with dark blue fur and is a tsundere"

# --- Data Structures ---
@dataclass
class Conversation:
    channel_id: int
    history: List[Dict[str, Any]] = field(default_factory=list)

    def add_message(self, role: str, content: Any):
        self.history.append({"role": role, "content": content})

    def reset_history(self, system_prompt: str = DEFAULT_SYSTEM_PROMPT):
        self.history = [{"role": "system", "content": system_prompt}]

    def get_history(self):
        return self.history

# --- Command Line Arguments ---
parser = argparse.ArgumentParser(description="Aoi Discord Bot")
parser.add_argument('--base_url', type=str, required=True,
                    help='The base URL for the OpenAI API.')
parser.add_argument('--discord_token', type=str, required=True,
                    help='The Discord bot token.')
args = parser.parse_args()

# --- Bot Setup ---
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

# --- Data Storage ---
conversation_history: Dict[int, Conversation] = {}  # Keyed by channel ID

# --- OpenAI Client ---
client = AsyncOpenAI(
    base_url=args.base_url,
    api_key=OPENAI_API_KEY,
)

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

    if bot.user.mentioned_in(message):
        channel_id = message.channel.id
        user_message_text = message.content.replace(f'<@!{bot.user.id}>', 'Aoi').strip()

        if channel_id not in conversation_history:
            conversation_history[channel_id] = Conversation(channel_id=channel_id)
            conversation_history[channel_id].reset_history()

        conversation = conversation_history[channel_id]

        # Prepare content for OpenAI API
        openai_content = []
        if user_message_text:
            openai_content.append({"type": "text", "text": user_message_text})

        if message.attachments:
            async with aiohttp.ClientSession() as session:
                for attachment in message.attachments:
                    if attachment.content_type and "image" in attachment.content_type:
                        try:
                            async with session.get(attachment.url) as resp:
                                if resp.status == 200:
                                    image_data = await resp.read()
                                    base64_image = base64.b64encode(image_data).decode('utf-8')
                                    image_url = f"data:{attachment.content_type};base64,{base64_image}"
                                    openai_content.append({
                                        "type": "image_url",
                                        "image_url": {"url": image_url}
                                    })
                        except Exception as e:
                            print(f"Error downloading or processing attachment: {e}")


        if not openai_content: # Don't send empty messages
            return

        # Add to conversation history
        if len(openai_content) == 1 and openai_content[0]['type'] == 'text':
             # Keep original format for text-only messages for compatibility
            conversation.add_message("user", openai_content[0]['text'])
        else:
            conversation.add_message("user", openai_content)


        try:
            async with message.channel.typing():
                response = await client.chat.completions.create(
                    model="gpt-4", # Or any other model you are using
                    messages=conversation.get_history()
                )
                bot_response = response.choices[0].message.content
                conversation.add_message("assistant", bot_response)
                # Split into chunks for discord to prevent message too long
                chunks = [bot_response[i:i+2000] for i in range(0, len(bot_response), 2000)]
                await message.reply(chunks[0])
                for chunk in chunks[1:]:
                    await message.channel.send(chunk)
        except Exception as e:
            print(f"An error occurred: {e}")
            conversation.history.pop() # Remove user message on error
            await message.reply("Sorry, I had a little hiccup. Baka!")


# --- Slash Commands ---
@bot.tree.command(name="newchat", description="Start a new chat with a new system prompt.")
async def newchat(interaction: discord.Interaction, prompt: str = None):
    channel_id = interaction.channel_id
    
    system_prompt = prompt
    if system_prompt is None:
        system_prompt = DEFAULT_SYSTEM_PROMPT

    if channel_id not in conversation_history:
        conversation_history[channel_id] = Conversation(channel_id=channel_id)

    conversation_history[channel_id].reset_history(system_prompt)
    
    if prompt is None:
        await interaction.response.send_message("Starting a new chat with the default prompt.")
    else:
        await interaction.response.send_message(f'Starting a new chat with the prompt: "{prompt}"')


# --- Running the Bot ---
if __name__ == "__main__":
    bot.run(args.discord_token)
