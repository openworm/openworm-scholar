import os
import re
from arxiv_cli import Client as ArxivClient
from slackclient import SlackClient
from urllib.parse import quote_plus as urlquote_plus

from wsgiref.simple_server import make_server
from pyramid.config import Configurator
from pyramid.response import Response

from recurrent import RecurringEvent
from datetime import datetime
from pytz import timezone
from subprocess import Popen, PIPE as subproc_PIPE


api_key = os.environ.get('SLACK_API_KEY')


# # Post a message
# c.api_call('chat.postEphemeral',
           # channel='#bot-test',
           # text='Hello world')

# c.api_call('chat.postEphemeral',
           # channel='#bot-test',
           # text='Hello world')


class Content(object):
    ident = 'owscholar:content:Content'
    """
    A wrapper for functionality about different types of presentation format,
    like HTML, Slack's markdown-like syntax, ReStructuredText, etc.
    """

    def __init__(self, s):
        """
        Create a Content from the given string.
        """

    @classmethod
    def quote(cls, s):
        """
        Quote the given string so that it can be displayed literally when
        presented for this content
        """
        return s


class UnicodeStringContent(Content):
    ident = 'owscholar:content:UnicodeStringContent'

    def __init__(self, s):
        super(UnicodeStringContent, self).__init__(s)
        self.str_content = s

    def render(self):
        return self.str_content


class SlackMessageContent(UnicodeStringContent):
    ident = 'owscholar:content:SlackMessageContent'


class MessageFragment(object):
    def __init__(self, frag, frag_type):
        """
        Parameters
        ----------
        frag : Content
            A piece of content which is not necessarily considered to be a
            complete document for the content type (e.g., a ``<div>`` element
            for an HtmlContent)
        frag_type : type(Content)
            The originally requested type for the content, which may differ
            from the type of frag
        """
        self.frag = frag
        self.frag_type = frag_type

    def render(self):
        return self.frag.render()


class Query(object):
    def msg_format(self, content_type):
        """ Returns a MessageFragment in the format given """
        return MessageFragment(content_type(content_type.quote(str(self))), content_type)

    def execute(self):
        pass


class ArxivQuery(Query):
    def __init__(self, s):
        self.search_query = s
        self._client = ArxivClient()

    def msg_format(self, content_type):
        if issubclass(content_type, SlackMessageContent):
            link_text = 'ArXiv Query:<http://export.arxiv.org/api/query?search_query={}|{}>'
            return MessageFragment(content_type(link_text.format(urlquote_plus(self.search_query),
                                                                 self.search_query)),
                                   content_type)
        else:
            return super(ArxivQuery, self).msg_format(content_type)

    def execute(self):
        r = self._client.find(self.search_query)
        return ArxivQueryResponse(r, self)


class Author(object):

    def __init__(self, name, affil=None, email=None):
        self.name = name
        self.affil = affil
        self.email = email


class ArxivAuthor(Author):
    def __init__(self, author_object):
        super(ArxivAuthor, self).__init__(author_object['name'])


class ArxivQueryResponse(object):
    def __init__(self, response_object, query):
        self._response = response_object
        self._query = query

    def events(self):
        for e in self._response['entries']:
            yield ArxivPublicationEvent(title=e['title'],
                                        link=e['link'],
                                        authors=[ArxivAuthor(a) for a in e['authors']],
                                        query=self._query)


class Event(object):
    def msg_format(self, content_type):
        return MessageFragment(content_type('nothing'), content_type)


class PublicationEvent(Event):
    def __init__(self, title, authors, link):
        self.title = title
        self.authors = authors
        self.link = link


class ArxivPublicationEvent(PublicationEvent):

    def __init__(self, query, *args, **kwargs):
        super(ArxivPublicationEvent, self).__init__(*args, **kwargs)
        self.query = query

    def msg_format(self, content_type):
        if issubclass(content_type, SlackMessageContent):
            fmt = 'New publication "{}" by _{}_\nMatched by {}'
            msg_str = fmt.format(self.title,
                                 ', '.join(a.name for a in self.authors),
                                 self.query.msg_format(content_type).render())
            return MessageFragment(content_type(msg_str), content_type)
        else:
            return MessageFragment(UnicodeStringContent(str(self)), content_type)


class Duration(object):
    """ A span of time """


class Period(object):
    """ A duration with an implicit cycle """


class Schedule(object):
    """ A schedule. A set of Periods, each with a start and end date-time """


class SearchScheduler(object):
    """ Schedules searches to be performed at regular intervals """

    def schedule(query, sched):
        """ add a search schedule for the given query """


class User(object):
    def __init__(self):
        self.time_zone = None


class SlackUser(User):
    def __init__(self, slack_ob, *args, **kwargs):
        super(SlackUser, self).__init__(*args, **kwargs)
        self._slack_ob = slack_ob
        self.time_zone = slack_ob['tz']


def send_message(api_key_or_client, channel, s, thread=None):
    if isinstance(api_key, str):
        sc = SlackClient(api_key)
    else:
        sc = api_key_or_client
    print('sending to thread', thread)
    sc.api_call('chat.postMessage',
                channel=channel,
                text=s,
                **{'thread_ts': x for x in (thread,) if thread})


SEARCH_TARGET_NAMES = ['Arxiv', 'PubMed']
AND_OR_COMMA_RGX_STR = r'(\s*,?\s+and\s+|\s*,\s*)'
PLACES_RGX_STR = "({})".format("|".join(re.escape(nom) for nom in SEARCH_TARGET_NAMES))
MSG_RGX_STR = r'''search \s+ for \s+ (?P<query>.*)\s+
                  (on|at) \s+ (?P<targets>{places} ( {and_or_comma} {places})*)
                  (\s+(?P<schedule> .+?))?$'''.format(places=PLACES_RGX_STR,
                                                      and_or_comma=AND_OR_COMMA_RGX_STR)

MSG_RGX = re.compile(MSG_RGX_STR, flags=re.VERBOSE | re.IGNORECASE)


def slack_events(request):
    # print(SlackClient)
    # print(request.environ, dir(request))
    # print(request.context)
    bod = request.json_body
    bot_token = os.environ.get('SLACK_BOT_TOKEN')
    if bod['token'] != bot_token:
        return Response(status=304)

    evt = bod['event']
    msg = evt['text']
    edited = evt.get('edited')
    if edited:
        user_ts = edited['ts']
    else:
        user_ts = evt['ts']

    print('headers', dict(request.headers))
    retry_count = request.headers.get('X-Slack-Retry-Num')
    if retry_count is not None and int(retry_count) > 0:
        thread = evt['ts']
    else:
        thread = None

    slack_api_key = os.environ.get('SLACK_API_KEY')
    slack_client = SlackClient(slack_api_key)
    user_ts = float(user_ts)
    # Parsing natural language with regex...we can add a context free grammar later...
    md = MSG_RGX.search(msg)
    if md:
        tgts = re.split(AND_OR_COMMA_RGX_STR, md.group('targets'))
        found_tgts = []
        for t in tgts:
            for s in SEARCH_TARGET_NAMES:
                if s.lower() == t.lower():
                    found_tgts.append(s)
        res = slack_client.api_call('users.info', user=evt['user'])
        tz = timezone(res['user']['tz'])
        sched = RecurringEvent(now_date=datetime.fromtimestamp(user_ts, tz))
        rrule = sched.parse(md.group('schedule'))
        reply = 'OK, <@{}>, I will search for "{}" on {} with a schedule of "{}"'
        reply = reply.format(evt['user'],
                             md.group('query'),
                             ", ".join(found_tgts),
                             str(rrule))
    else:
        with Popen(["fortune"], stdout=subproc_PIPE) as proc:
            fortune = proc.stdout.read().decode('utf-8')
        reply = 'Sorry, <@{}>, I don\'t know about that, but think about this:\n{}'
        reply = reply.format(evt['user'], fortune)

    send_message(slack_client, evt['channel'], reply, thread)
    return Response('')


if __name__ == '__main__':
    with Configurator() as config:
        config.add_route('slack_events', '/events')
        config.add_view(slack_events, route_name='slack_events')
        app = config.make_wsgi_app()

    server = make_server('0.0.0.0', 8080, app)
    server.serve_forever()

    # sc = SlackClient(api_key)

    # aq = ArxivQuery('ti:C and ti:elegans or abs:C and abs:elegans')
    # r = aq.execute()

    # for pe in r.events():
        # sc.api_call('chat.postMessage',
                    # channel='#bot-test',
                    # text=pe.msg_format(SlackMessageContent).render())
