import discord
from discord.ext import commands
from openai import AsyncOpenAI
import os
import base64
import aiohttp
import argparse

# --- Configuration ---
OPENAI_API_KEY = "eh"
DEFAULT_SYSTEM_PROMPT = "you are a catboy named Aoi with dark blue fur and is a tsundere"

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
conversation_history = {}  # Keyed by channel ID

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
            conversation_history[channel_id] = [
                {"role": "system", "content": DEFAULT_SYSTEM_PROMPT}
            ]

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
            conversation_history[channel_id].append({"role": "user", "content": openai_content[0]['text']})
        else:
            conversation_history[channel_id].append({"role": "user", "content": openai_content})


        try:
            async with message.channel.typing():
                response = await client.chat.completions.create(
                    model="gpt-4", # Or any other model you are using
                    messages=conversation_history[channel_id]
                )
                bot_response = response.choices[0].message.content
                conversation_history[channel_id].append({"role": "assistant", "content": bot_response})
                await message.reply(bot_response)
        except Exception as e:
            print(f"An error occurred: {e}")
            conversation_history[channel_id].pop() # Remove user message on error
            await message.reply("Sorry, I had a little hiccup. Baka!")


# --- Slash Commands ---
@bot.tree.command(name="newchat", description="Start a new chat with a new system prompt.")
async def newchat(interaction: discord.Interaction, prompt: str = None):
    channel_id = interaction.channel_id
    
    system_prompt = prompt
    if system_prompt is None:
        system_prompt = DEFAULT_SYSTEM_PROMPT

    conversation_history[channel_id] = [
        {"role": "system", "content": system_prompt}
    ]
    
    if prompt is None:
        await interaction.response.send_message("Starting a new chat with the default prompt.")
    else:
        await interaction.response.send_message(f'Starting a new chat with the prompt: "{prompt}"')


# --- Running the Bot ---
if __name__ == "__main__":
    bot.run(args.discord_token)
