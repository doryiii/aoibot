import collections
import discord
from discord.ext import commands
import os
import argparse
from typing import List, Dict, Any

from llm_client import Conversation
from database import Database

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
class AoiBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    async def setup_hook(self):
        self.db = Database.get()
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = AoiBot(command_prefix="/", intents=intents)


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
        messages.append(message.id)
    await message.add_reaction("🔁")
    await message.add_reaction("❌")
    return messages

async def webhook(channel):
    name = f'aoi-{channel.id}'
    channel_hooks = [
        hook for hook in (await channel.webhooks()) if hook.name == name
    ]
    if not channel_hooks:
        return await channel.create_webhook(name=f'aoi-{channel.id}')
    return channel_hooks[0]

async def clear_reactions(channel, message_ids):
    for message_id in message_ids:
        try:
            message = await channel.fetch_message(message_id)
            await message.clear_reaction("🔁")
            await message.clear_reaction("❌")
        except (discord.NotFound, discord.Forbidden):
            pass # Ignore if message is not found or we don't have perms


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
    conversation = await Conversation.get(channel.id, args.base_url, bot.db)
    user_message = message.content
    if user_message.startswith(bot_tag):
        user_message = user_message[len(bot_tag):]
    user_message = user_message.replace(bot_tag, conversation.bot_name).strip()
    print(f'{channel.id}> {message.author.name}: {user_message}')

    media = []
    if message.attachments:
        for attachment in message.attachments:
            media.append((attachment.content_type, attachment.url))

    try:
        async with channel.typing():
            response = await conversation.generate(user_message, media)
        await clear_reactions(channel, conversation.last_messages)
        conversation.last_messages = await discord_send(
            channel, response, conversation.bot_name,
        )
        await conversation.save()
    except Exception as e:
        print(f"An error occurred: {e}")
        await message.reply("Sorry, I had a little hiccup. Baka!")

@bot.event
async def on_reaction_add(reaction, user):
    if reaction.emoji not in ("🔁", "❌") or user == bot.user:
        return
    message = reaction.message
    channel = message.channel
    conversation = await Conversation.get(channel.id, args.base_url, bot.db)
    if message.id not in conversation.last_messages:
        await reaction.clear()
        return
    print(f"_ {user}: {reaction}")

    try:
        async with channel.typing():
            try:
                messages = [
                    await channel.fetch_message(message_id)
                    for message_id in conversation.last_messages
                ]
            except (discord.NotFound, discord.Forbidden) as e:
                # don't do anything if any message in the list is not found
                await reaction.clear()
                return
            for message in messages:
                await message.delete()

            if reaction.emoji == "❌":
                await conversation.pop()
            elif reaction.emoji == "🔁":
                response = await conversation.regenerate()
                conversation.last_messages = await discord_send(
                    channel, response, conversation.bot_name,
                )
                await conversation.save()
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
    old_convo = await Conversation.get(
        channel_id, args.base_url, bot.db, create_if_not_exist=False,
    )
    if old_convo:
        await clear_reactions(interaction.channel, old_convo.last_messages)
    conversation = await Conversation.create(
        channel_id, args.base_url, bot.db, prompt
    )
    await interaction.followup.send(
        f'Starting a new chat with {conversation.bot_name}: '
        f'"{conversation.history[0]["content"]}"'
    )

@bot.tree.command(
    name="changeprompt",
    description="Change the current chat's system prompt."
)
async def changeprompt(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    channel_id = interaction.channel_id
    conversation = await Conversation.get(channel_id, args.base_url, bot.db)
    await conversation.update_prompt(prompt)
    await interaction.followup.send(
        f'Now chatting with {conversation.bot_name}: "{prompt}"'
    )


# --- Running the Bot ---
if __name__ == "__main__":
    bot.run(args.discord_token)

