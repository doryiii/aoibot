import unittest
import os
import json
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

from tools import get_time, web_fetch, web_search, Tools


class ToolsTest(unittest.IsolatedAsyncioTestCase):
  def test_get_time(self):
    result = get_time()
    self.assertIsInstance(result, str)
    # Result should contain the current weekday name
    today = datetime.now().strftime('%A')
    self.assertIn(today, result)

  def test_tools_spec(self):
    tools = Tools()
    specs = tools.tools()
    self.assertEqual(len(specs), 3)
    # Map specs by function name for easier lookup
    specs_by_name = {s['function']['name']: s for s in specs}

    # get_time has no parameters, so parameters should be an empty dict
    get_time_spec = specs_by_name['get_time']
    self.assertEqual(get_time_spec['type'], 'function')
    self.assertEqual(get_time_spec['function']['parameters'], {})

    # web_fetch should have a required 'url' parameter of type string
    wf_spec = specs_by_name['web_fetch']
    wf_params = wf_spec['function']['parameters']
    self.assertIn('properties', wf_params)
    self.assertIn('url', wf_params['properties'])
    self.assertEqual(wf_params['properties']['url']['type'], 'string')
    self.assertEqual(wf_params['properties']['url']['description'],
      'the webpage URL to fetch')
    self.assertIn('url', wf_params['required'])

    # web_search should have 'query' (required) and 'num_results' (optional)
    ws_spec = specs_by_name['web_search']
    ws_params = ws_spec['function']['parameters']
    self.assertIn('properties', ws_params)
    self.assertIn('query', ws_params['properties'])
    self.assertIn('num_results', ws_params['properties'])
    self.assertEqual(ws_params['properties']['query']['type'], 'string')
    self.assertEqual(ws_params['properties']['query']['description'],
      'the web search query')
    self.assertEqual(ws_params['properties']['num_results']['type'], 'integer')
    self.assertEqual(ws_params['properties']['num_results']['description'],
      'how many pages to get. Default 5')
    self.assertIn('query', ws_params['required'])
    self.assertNotIn('num_results', ws_params['required'])

  async def test_tools_call(self):
    tools = Tools()
    # Add dummy async and sync functions to the registry
    async def dummy_async(x):
      return x * 2

    def dummy_sync(y):
      return y + 1

    tools._tools['dummy_async'] = dummy_async
    tools._tools['dummy_sync'] = dummy_sync
    result_async = await tools.call('dummy_async', x=5)
    self.assertEqual(result_async, 10)
    result_sync = await tools.call('dummy_sync', y=7)
    self.assertEqual(result_sync, 8)
    with self.assertRaises(ValueError):
      await tools.call('nonexistent')

  async def test_web_fetch(self):
    # Mock aiohttp.ClientSession and its GET request using async context manager semantics
    with patch('tools.aiohttp.ClientSession') as mock_client_class:
      # Mock session as async context manager
      mock_session = AsyncMock()
      mock_session.__aenter__ = AsyncMock(return_value=mock_session)
      mock_session.__aexit__ = AsyncMock(return_value=None)
      mock_response = AsyncMock()
      mock_response.__aenter__ = AsyncMock(return_value=mock_response)
      mock_response.__aexit__ = AsyncMock(return_value=None)
      mock_response.raise_for_status = Mock()
      mock_response.text = AsyncMock(return_value='<h1>Hello</h1>')
      # session.get returns the mock response (as async context manager)
      mock_session.get = Mock(return_value=mock_response)
      # Ensure aiohttp.ClientSession returns our mock session
      mock_client_class.return_value = mock_session
      result = await web_fetch('example.com')
      # The real html2text conversion should be applied to the fetched HTML
      expected = '# Hello\n\n'
      self.assertEqual(result, expected)
      mock_session.get.assert_called_once_with('https://example.com')

  async def test_web_search(self):
    # Mock API response data
    api_response = {
        'data': {
            'webPages': {
                'value': [
                    {'name': 'Page1', 'url': 'http://page1.com', 'summary': 'Summary1'},
                    {'name': 'Page2', 'url': 'http://page2.com', 'snippet': 'Snippet2'},
                    {'name': 'Page3', 'url': 'http://page3.com'}
                ]
            }
        }
    }
    with patch.dict(os.environ, {'LANGSEARCH_API_KEY': 'testkey'}):
      with patch('tools.aiohttp.ClientSession') as mock_client_class:
        # Mock session as async context manager
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_response = AsyncMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_response.raise_for_status = Mock()
        mock_response.json = AsyncMock(return_value=api_response)
        # session.post returns the mock response
        mock_session.post = Mock(return_value=mock_response)
        # Ensure aiohttp.ClientSession() returns our mock session
        mock_client_class.return_value = mock_session
        result = await web_search('test query', num_results=2)
        cleaned = json.loads(result)
        expected = [
            {'name': 'Page1', 'url': 'http://page1.com', 'summary': 'Summary1'},
            {'name': 'Page2', 'url': 'http://page2.com', 'summary': 'Snippet2'},
            {'name': 'Page3', 'url': 'http://page3.com', 'summary': None}
        ]
        self.assertEqual(cleaned, expected)
        # Verify request payload and headers
        mock_session.post.assert_called_once()
        args, kwargs = mock_session.post.call_args
        self.assertEqual(args[0], 'https://api.langsearch.com/v1/web-search')
        self.assertEqual(kwargs['json']['query'], 'test query')
        self.assertEqual(kwargs['json']['count'], 2)
        self.assertTrue(kwargs['json']['summary'])
        self.assertIn('Authorization', kwargs['headers'])
