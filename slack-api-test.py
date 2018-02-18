import os
from slackclient import SlackClient

api_key = os.environ['SLACK_API_KEY']

c = SlackClient(api_key)

TEST_CHANNEL_NAME = '#bot-test'


def test_post_message():
    x = c.api_call('chat.postMessage',
                   channel=TEST_CHANNEL_NAME,
                   text='Hello world')
    assert x['ok']


def test_post_message_as_user():
    x = c.api_call('chat.postMessage',
                   channel=TEST_CHANNEL_NAME,
                   as_user=True,
                   text='Hello world')
    assert 'username' not in x['message']


def test_post_message_not_as_user():
    x = c.api_call('chat.postMessage',
                   channel=TEST_CHANNEL_NAME,
                   as_user=False,
                   text='Hello world')
    assert 'username' in x['message']


def test_post_message_no_as_user():
    x = c.api_call('chat.postMessage',
                   channel=TEST_CHANNEL_NAME,
                   text='Hello world')
    assert 'username' in x['message']


def test_post_message_to_thread():
    x = c.api_call('chat.postMessage',
                   channel=TEST_CHANNEL_NAME,
                   text='Hello world')
    ts = x['ts']
    x = c.api_call('chat.postMessage',
                   channel=TEST_CHANNEL_NAME,
                   thread_ts=ts,
                   text='Hello, hello world')
    assert x['ok']


def test_post_message_to_thread_broadcast():
    x = c.api_call('chat.postMessage',
                   channel=TEST_CHANNEL_NAME,
                   text='Hello world')
    ts = x['ts']
    x = c.api_call('chat.postMessage',
                   channel=TEST_CHANNEL_NAME,
                   thread_ts=ts,
                   reply_broadcast=True,
                   text='Broadcast: Reply to: "Hello world"')
    assert x['ok']
    assert x['message']['is_thread_broadcast']


def test_post_ephemeral_real_user():
    x = c.api_call('chat.postEphemeral',
                   channel=TEST_CHANNEL_NAME,
                   user='U3ZT5TL1Z',
                   text='Hello world')
    assert x['ok']


def test_post_ephemeral_fake_user():
    x = c.api_call('chat.postEphemeral',
                   channel=TEST_CHANNEL_NAME,
                   user='notauser',
                   text='Hello world')

    assert not x['ok']
    assert x['error'] == 'user_not_in_channel'


def test_post_ephemeral_no_user():
    x = c.api_call('chat.postEphemeral',
                   channel=TEST_CHANNEL_NAME,
                   text='Hello world')
    assert not x['ok']
    assert x['error'] == 'user_not_in_channel'


def test_post_links():
    x = c.api_call('chat.postMessage',
                   channel=TEST_CHANNEL_NAME,
                   text='http://example.org')
    assert x['ok']


def test_post_markdown_link():
    x = c.api_call('chat.postMessage',
                   channel=TEST_CHANNEL_NAME,
                   text='<http://example.org|link>')
    assert x['ok']


def test_post_markdown_link_no_unfurled_links():
    x = c.api_call('chat.postMessage',
                   channel=TEST_CHANNEL_NAME,
                   unfurl_links=False,
                   text='<http://example.org|link>')
    assert x['ok']


def test_post_link_no_unfurled_links():
    x = c.api_call('chat.postMessage',
                   channel=TEST_CHANNEL_NAME,
                   unfurl_links=False,
                   text='http://example.org')
    assert x['ok']
