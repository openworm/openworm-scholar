import unittest
from unittest.mock import MagicMock, patch, ANY, DEFAULT

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


class ViewTests(unittest.TestCase):

    def __init__(self, *args, **kwargs):
        super(ViewTests, self).__init__(*args, **kwargs)
        self.patchers = []

    def patch_object(self, ob, attr):
        patcher = patch.object(ob, attr)
        self.patchers.append(patcher)
        return patcher.start()

    def setUp(self):
        self.mock_os = self.patch_object(slack_bot, 'os')
        self.mock_slack = self.patch_object(slack_bot, 'SlackClient')
        self.config = testing.setUp()
        self.bot_token = 'bottok'
        self.mock_os.environ = {'SLACK_API_KEY': 'key', 'SLACK_BOT_TOKEN': self.bot_token}
        self.uname = 'Uh092hp20h'
        request = MagicMock()
        request.headers = {}
        request.json_body = {'token': self.bot_token,
                'event': {'text': 'blah', 'ts': '1.0', 'user': self.uname, 'channel': 'chan'}}
        self.mock_request = request

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        testing.tearDown()

    def test_message_sent_to_user_at_channel_1(self):
        slack_events(self.mock_request)
        self.mock_slack().api_call.assert_called_with('chat.postMessage', channel='chan', text=Contains('<@'+self.uname+'>'))

    def test_message_sent_to_user_at_channel_2(self):
        target = random.choice(slack_bot.SEARCH_TARGET_NAMES)
        msg = 'Search for grapes at ' + target
        self.mock_request.json_body['event']['text'] = msg
        def call(message, user=None, **kwargs):
            if message == 'users.info' and user is not None:
                return {'user': {'tz': 'America/Chicago'}}
            else:
                return DEFAULT
        self.mock_slack().api_call.side_effect = call
        slack_events(self.mock_request)
        self.mock_slack().api_call.assert_called_with('chat.postMessage', channel='chan', text=Contains('<@'+self.uname+'>'))

    def test_store(self):
        target = random.choice(slack_bot.SEARCH_TARGET_NAMES)
        msg = 'Search for grapes at ' + target
        self.mock_request.json_body['event']['text'] = msg
        def call(message, user=None, **kwargs):
            if message == 'users.info' and user is not None:
                return {'user': {'tz': 'America/Chicago'}}
            else:
                return DEFAULT
        self.mock_slack().api_call.side_effect = call
        slack_events(self.mock_request)
        self.mock_slack().api_call.assert_called_with('chat.postMessage', channel='chan', text=Contains('<@'+self.uname+'>'))

