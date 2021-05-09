import unittest
from unittest.mock import MagicMock, patch, DEFAULT

import random
from pyramid import testing
from .slack_bot import slack_events, EventHandler, ListSearchScheduler
from . import slack_bot
import re
import tempfile

from zodburi import resolve_uri
from ZODB.DB import DB
from persistent.dict import PersistentDict
import transaction


class Matches(object):
    def __init__(self, r):
        self.rgx = re.compile(r)

    def __eq__(self, other):
        return self.rgx.search(other) is not None

    def __ne__(self, other):
        return not self.rgx.search(other) is not None

    def __str__(self):
        return str(self.rgx)

    def __repr__(self):
        return f'Matches({self.rgx.pattern!r})'


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
        self.mock_slack = self.patch_object(slack_bot, 'slack').WebClient
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
        self.mock_slack().api_call.assert_called_with('chat.postMessage',
                                                      channel='chan',
                                                      text=Contains('<@'+self.uname+'>'))

    def test_message_without_schedule_defaults_daily(self):
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
        self.mock_slack().api_call.assert_called_with('chat.postMessage',
                                                      channel='chan',
                                                      text=Matches('RRULE:.*FREQ=DAILY'))

    @unittest.expectedFailure
    def test_message_daily_at_same_time_spreads_out(self):
        """
        Given a broad specification like 'daily', we can spread out executions
        so that our server experiences less 'bursty' load, and ultimately uses
        resources better given an 'always-on' configuration

        Essentially, if two overlapping schedules are requested, one should
        query starting from now, but the other should be offset slightly ahead
        in time. It should be *ahead* since we still want the first query in
        this schedule to execute soon.
        """
        self.fail("Not implemented")

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
        self.mock_slack().api_call.assert_called_with(
                'chat.postMessage', channel='chan', text=Contains('<@'+self.uname+'>'))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.uri = 'file://{}/db.zdb?connection_cache_size=200'.format(self.tempdir.name)
        self.open()

    def tearDown(self):
        self.conn.close()
        self.db.close()
        self.tempdir.cleanup()

    def open(self):
        storage_factory, dbkw = resolve_uri(self.uri)
        storage = storage_factory()
        self.db = DB(storage, **dbkw)
        self.conn = self.db.open()
        transaction.begin()

    def reopen(self):
        transaction.commit()
        self.conn.close()
        self.db.close()
        self.open()

    def test_persist_simple(self):
        root = self.conn.root()
        root['aba'] = PersistentDict()
        root['aba']['maba'] = 3
        self.reopen()
        root = self.conn.root()
        self.assertEqual(root['aba']['maba'], 3)

    def test_persist_EventHandler(self):
        root = self.conn.root()
        eh = EventHandler()
        root['event'] = eh
        self.reopen()
        root = self.conn.root()
        self.assertEqual(eh, root['event'])

    def test_persist_ListSearchScheduler_empty(self):
        root = self.conn.root()
        ss = ListSearchScheduler()
        root['sched'] = ss
        self.reopen()
        root = self.conn.root()
        self.assertEqual(ss, ListSearchScheduler())

    def test_persist_ListSearchScheduler_timefunc(self):
        from time import time
        root = self.conn.root()
        ss = ListSearchScheduler()
        root['sched'] = ss
        self.reopen()
        root = self.conn.root()
        self.assertEqual(root['sched'].timefunc, time)

    def test_persist_ListSearchScheduler_is_running(self):
        root = self.conn.root()
        ss = ListSearchScheduler()
        root['sched'] = ss
        self.reopen()
        root = self.conn.root()
        self.assertEqual(root['sched'].is_running, False)

    def test_persist_ListSearchScheduler_set_timefunc(self):
        from time import time
        ss = ListSearchScheduler()
        ss.timefunc = time
