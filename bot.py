import collections
import discord
from discord.ext import commands
import os
import argparse
from typing import List, Dict, Any

from llm_client import Conversation

# --- Configuration ---
DEFAULT_AVATAR = "https://cdn.discordapp.com/avatars/1406466525858369716/f1dfeaf2a1c361dbf981e2e899c7f981?size=256"

# --- Command Line Arguments ---
parser = argparse.ArgumentParser(description="Aoi Discord Bot")
parser.add_argument(
    '--base_url', type=str, required=True,
    help='The base URL for the OpenAI API.',
)
parser.add_argument(
    '--discord_token', type=str, required=True,
    help='The Discord bot token.',
)
args = parser.parse_args()

# --- Bot Setup ---
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)


# --- Helpers ---
async def discord_send(channel, text, name, avatar=DEFAULT_AVATAR):
    chunks = [text[i:i+2000] for i in range(0, len(text), 2000)]
    messages = []
    for chunk in chunks:
        if channel.guild:
            hook = await webhook(channel)
            message = await hook.send(
                content=chunk,
                username=name,
                avatar_url=avatar,
                wait=True,
            )
        else:
            message = await channel.send(content=chunk)
        messages.append(message)
    return messages


# --- Data Storage ---
# Keyed by channel ID
conversations = {}
_webhooks = {}
async def webhook(channel):
    if channel.id not in _webhooks:
        hook = await channel.create_webhook(name=f'aoi-{channel.id}')
        _webhooks[channel.id] = hook
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
    if channel.id not in conversations:
        conversations[channel.id] = await Conversation.create(args.base_url)
    conversation = conversations[channel.id]
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
            response = await conversation.generate(user_message, media)
            conversation.last_messages = await discord_send(
                channel, response, conversation.bot_name,
            )
    except Exception as e:
        print(f"An error occurred: {e}")
        await message.reply("Sorry, I had a little hiccup. Baka!")

@bot.event
async def on_reaction_add(reaction, user):
    if reaction.emoji != "🔁":
        return
    message = reaction.message
    channel = message.channel
    conversation = conversations[channel.id]
    if message not in conversation.last_messages:
        await reaction.clear()
        return
    print(f"_ {user}: {reaction}")

    try:
        async with channel.typing():
            for message in conversation.last_messages:
                await message.delete()
            response = await conversation.regenerate()
            conversation.last_messages = await discord_send(
                channel, response, conversation.bot_name,
            )
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
    conversation = await Conversation.create(args.base_url, prompt)
    conversations[channel_id] = conversation
    await interaction.followup.send(
        f'Starting a new chat with {conversation.bot_name}: "{prompt}"'
    )


# --- Running the Bot ---
if __name__ == "__main__":
    bot.run(args.discord_token)
