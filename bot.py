import argparse
import os

import discord
from discord.ext import commands
from openai import AsyncOpenAI

from conversations import ConversationManager
from database import Database

# --- Command Line Arguments ---
parser = argparse.ArgumentParser(description='Aoi Discord Bot')
parser.add_argument(
    '--base_url', default='http://localhost:8080/v1',
    help='The base URL for the OpenAI API server.',
)
parser.add_argument(
    '--model', default='', help='The model to use from OpenAI API.',
)
parser.add_argument(
    '--default_prompt',
    default='you are a catboy named Aoi with dark blue fur and is a tsundere',
    help='Default system prompt when not given in chat.',
)
parser.add_argument(
    '--default_avatar',
    default='https://cdn.discordapp.com/avatars/1406466525858369716/f1dfeaf2a1c361dbf981e2e899c7f981?size=256',
    help='Default avatar to use.',
)
parser.add_argument(
    '--db', default='conversations.db', help='SQLite DB to use.',
)
args = parser.parse_args()

# --- Bot Setup ---

class AoiBot(commands.Bot):
    async def setup_hook(self):
        db = Database.get(args.db)
        openai = AsyncOpenAI(
            base_url=args.base_url,
            api_key=os.environ.get("OPENAI_API_KEY") or ""
        )
        self.manager = ConversationManager(
            openai, args.model, db, args.default_prompt,
        )
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = AoiBot(command_prefix='/', intents=intents)


# --- Helpers ---
async def discord_send(channel, text, name, avatar=args.default_avatar):
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
    await message.add_reaction('🔁')
    await message.add_reaction('❌')
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
            await message.clear_reaction('🔁')
            await message.clear_reaction('❌')
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
    conversation = await bot.manager.get(channel.id)
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
        print(f'An error occurred: {e}')
        await message.reply('Sorry, I had a little hiccup. Baka!')

@bot.event
async def on_reaction_add(reaction, user):
    if reaction.emoji not in ('🔁', '❌') or user == bot.user:
        return
    message = reaction.message
    channel = message.channel
    conversation = await bot.manager.get(channel.id)
    if message.id not in conversation.last_messages:
        await reaction.clear()
        return
    print(f'{channel.id}_ {user}: {reaction}')

    try:
        try:
            messages = [
                await channel.fetch_message(message_id)
                for message_id in conversation.last_messages
            ]
        except (discord.NotFound, discord.Forbidden):
            # don't do anything if any message in the list is not found
            await reaction.clear()
            return
        for message in messages:
            await message.delete()

        if reaction.emoji == '❌':
            await conversation.pop()
        elif reaction.emoji == '🔁':
            async with channel.typing():
                response = await conversation.regenerate()
                conversation.last_messages = await discord_send(
                    channel, response, conversation.bot_name,
                )
                await conversation.save()
    except Exception as e:
        print(f'An error occurred: {e}')
        await channel.send('Sorry, I had a little hiccup. Baka!')


# --- Slash Commands ---
@bot.tree.command(
    name='newchat',
    description='Start a new chat with an optional system prompt.'
)
async def newchat(
    interaction: discord.Interaction,
    prompt: str = None,
    web_access: bool = False,
):
    await interaction.response.defer()
    channel_id = interaction.channel_id
    print(f'{channel_id}_ {interaction.user} newchat with: {prompt}')
    old_convo = await bot.manager.get(channel_id, create_if_missing=False)
    if old_convo:
        await clear_reactions(interaction.channel, old_convo.last_messages)
    conversation = await bot.manager.new_conversation(
        channel_id, prompt, web_access
    )
    await interaction.followup.send(
        f'Starting a new chat with {conversation.bot_name}: '
        f'"{conversation.prompt}"'
    )

@bot.tree.command(
    name='changeprompt',
    description='Change the system prompt of the current conversation.'
)
async def changeprompt(
    interaction: discord.Interaction,
    prompt: str,
    web_access: bool | None = None,
):
    await interaction.response.defer()
    channel_id = interaction.channel_id
    conversation = await bot.manager.get(channel_id)
    await conversation.update_prompt(prompt, web_access)
    await interaction.followup.send(
        f'Now chatting with {conversation.bot_name}: '
        f'"{conversation.prompt}"'
    )


# --- Running the Bot ---
if __name__ == '__main__':
    bot.run(os.environ.get("DISCORD_TOKEN") or "")
