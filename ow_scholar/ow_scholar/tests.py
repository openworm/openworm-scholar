import unittest
from unittest.mock import MagicMock, patch, ANY

import random
from pyramid import testing
from .slack_bot import slack_events
from . import slack_bot
import re


class Matches(object):
    def __init__(self, r):
        self.rgx = re.compile(r)

    def __eq__(self, other):
        return self.rgx.matches(other)

    def __ne__(self, other):
        return not self.rgx.matches(other)

    def __str__(self):
        return str(self.rgx)


class Contains(object):
    def __init__(self, s):
        self.s = s

    def __eq__(self, other):
        return self.s in other

    def __ne__(self, other):
        return self.s not in other

    def __repr__(self):
        return 'Contains(' + repr(self.s) + ')'

    def __str__(self):
        return self.s


@patch.object(slack_bot, 'SlackClient')
class ViewTests(unittest.TestCase):
    def setUp(self):
        self.config = testing.setUp()
        self.bot_token = 'bottok'

    def tearDown(self):
        testing.tearDown()

    def test_message_sent_to_user_at_channel_1(self, mock_slack):
        request = MagicMock()
        request.environ = {'SLACK_API_KEY': 'key', 'SLACK_BOT_TOKEN': self.bot_token}
        request.headers = {}
        uname = 'Uh092hp20h'
        request.json_body = {'token': self.bot_token,
                'event': {'text': 'blah', 'ts': '1.0', 'user': uname, 'channel': 'chan'}}
        slack_events(request)
        mock_slack().api_call.assert_called_with('chat.postMessage', channel='chan', text=Contains('<@'+uname+'>'))
        print(mock_slack.mock_calls)

    def test_message_sent_to_user_at_channel_2(self, mock_slack):
        request = MagicMock()
        request.environ = {'SLACK_API_KEY': 'key', 'SLACK_BOT_TOKEN': self.bot_token}
        request.headers = {}
        uname = 'Uh092hp20h'
        target = random.choice(slack_bot.SEARCH_TARGET_NAMES)
        msg = 'Search for grapes at ' + target
        request.json_body = {'token': self.bot_token,
                'event': {'text': msg, 'ts': '1.0', 'user': uname, 'channel': 'chan'}}
        slack_events(request)
        mock_slack().api_call.assert_called_with('chat.postMessage', channel='chan', text=Contains('<@'+uname+'>'))
        print(mock_slack.mock_calls)
