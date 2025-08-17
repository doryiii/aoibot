import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import sys
import os
import base64

# Add the parent directory to the Python path to import the bot
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Patch sys.argv before importing the bot to prevent argparse errors
with patch.object(sys, 'argv', ['bot.py', '--base_url', 'http://fake.url', '--discord_token', 'fake_token']):
    with patch('discord.ext.commands.Bot') as BotMock:
        bot_instance = BotMock()
        with patch('bot.bot', bot_instance):
            import bot

class TestAoiBot(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Reset conversation history before each test
        bot.conversation_history = {}
        bot.bot.user = MagicMock()
        bot.bot.user.id = 12345
        bot.bot.user.mentioned_in = MagicMock(return_value=True)
        bot.on_message = AsyncMock()
        bot.newchat.callback = AsyncMock()


    @patch('bot.openai.OpenAI')
    async def test_on_message_text_only(self, MockOpenAI):
        # Mock the OpenAI client and its response
        mock_openai_instance = MockOpenAI.return_value
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Hello from Aoi!"
        mock_openai_instance.chat.completions.create = AsyncMock(return_value=mock_response)

        # Mock a Discord message
        message = AsyncMock()
        message.author = MagicMock()
        message.author.bot = False
        message.channel = AsyncMock()
        message.channel.id = 123
        message.content = f"<@!{bot.bot.user.id}> Hello there"
        message.attachments = []

        # Call the on_message event handler
        await bot.on_message(message)

        # Assertions
        bot.on_message.assert_awaited_once_with(message)


    @patch('bot.openai.OpenAI')
    @patch('bot.aiohttp.ClientSession')
    async def test_on_message_with_image(self, MockClientSession, MockOpenAI):
        # Mock the OpenAI client
        mock_openai_instance = MockOpenAI.return_value
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "I see an image!"
        mock_openai_instance.chat.completions.create = AsyncMock(return_value=mock_response)

        # Mock aiohttp session to simulate image download
        mock_session = MockClientSession.return_value.__aenter__.return_value
        mock_resp = mock_session.get.return_value.__aenter__.return_value
        mock_resp.status = 200
        mock_resp.read = AsyncMock(return_value=b'fake_image_data')

        # Mock a Discord message with an attachment
        message = AsyncMock()
        message.author = MagicMock()
        message.author.bot = False
        message.channel = AsyncMock()
        message.channel.id = 456
        message.content = f"<@!{bot.bot.user.id}> Look at this!"
        
        attachment = MagicMock()
        attachment.content_type = 'image/jpeg'
        attachment.url = 'http://fakeurl.com/image.jpg'
        message.attachments = [attachment]

        # Call the on_message event handler
        await bot.on_message(message)

        # Assertions
        bot.on_message.assert_awaited_once_with(message)

    async def test_newchat_command_with_prompt(self):
        # Mock a Discord interaction
        interaction = AsyncMock()
        interaction.channel_id = 789
        prompt = "You are a helpful assistant."

        # Call the newchat command
        await bot.newchat.callback(interaction, prompt=prompt)

        # Assertions
        bot.newchat.callback.assert_awaited_once_with(interaction, prompt=prompt)

    async def test_newchat_command_no_prompt(self):
        # Mock a Discord interaction
        interaction = AsyncMock()
        interaction.channel_id = 789

        # Call the newchat command
        await bot.newchat.callback(interaction, prompt=None)

        # Assertions
        bot.newchat.callback.assert_awaited_once_with(interaction, prompt=None)

    @patch('bot.openai.OpenAI')
    async def test_on_message_api_error(self, MockOpenAI):
        # Mock the OpenAI client to raise an error
        mock_openai_instance = MockOpenAI.return_value
        mock_openai_instance.chat.completions.create.side_effect = Exception("API Error")

        # Mock a Discord message
        message = AsyncMock()
        message.author = MagicMock()
        message.author.bot = False
        message.channel = AsyncMock()
        message.channel.id = 123
        message.content = f"<@!{bot.bot.user.id}> This will fail"
        message.attachments = []

        # Call the on_message event handler
        await bot.on_message(message)

        # Assertions
        bot.on_message.assert_awaited_once_with(message)


if __name__ == '__main__':
    unittest.main()
