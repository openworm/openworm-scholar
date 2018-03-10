import os
import re
from arxiv_cli import Client as ArxivClient
from slackclient import SlackClient
from urllib.parse import quote_plus as urlquote_plus

from wsgiref.simple_server import make_server
from pyramid.config import Configurator
from pyramid.response import Response

from recurrent import RecurringEvent
from dateutil.rrule import rrulestr
from datetime import datetime
from pytz import timezone
from subprocess import Popen, PIPE as subproc_PIPE
from sched import scheduler
from time import time, sleep
from threading import Thread

import persistent
from persistent import Persistent
from persistent.list import PersistentList
from persistent.dict import PersistentDict


api_key = os.environ.get('SLACK_API_KEY')


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


class Query(Persistent):
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
        print("running arxiv query for: " + self.search_query)
        r = self._client.find(self.search_query)
        return ArxivQueryResponse(r, self)

    def validate(self):
        return True


class PubmedQuery(Query):
    def __init__(self, s):
        self.search_query = s

    def validate(self):
        return True


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


class SearchSchedule(object):
    """ A schedule for searches """

    def __init__(self, query, sched):
        """ add a search schedule for the given query """
        self.query = query
        self.sched = sched


class SearchScheduler(Persistent):
    """ Schedules searches to be performed at regular intervals """

    def add_schedule(self, query, sched, handler):
        """ add a search schedule for the given query """


def query_event(sched, search_sched, event_handler, priority=0):
    print("query_event", search_sched, event_handler, priority)
    def run():
        print("run", search_sched, event_handler, priority)
        response = search_sched.query.execute()
        for evt in response.events():
            event_handler(evt)
        query_event(sched, search_sched, event_handler, priority)
    now = datetime.now()
    delay = search_sched.sched.after(now) - now
    sched.enter(delay.total_seconds(), priority, run, ())
    return run


class EventHandler(object):
    """ Handles events, yo """
    def __call__(self, event):
        print("Handling event")
        print(event)


class ListSearchScheduler(SearchScheduler):

    def __init__(self, sched_list=None, timefunc=time, delayfunc=sleep, **kwargs):
        super(ListSearchScheduler, self).__init__(**kwargs)
        if sched_list is None:
            sched_list = []
        self._list = PersistentList(sched_list)
        self._v_timefunc = timefunc
        self._v_delayfunc = delayfunc
        self._v_thread = None
        self._v_sched = None
        self._v_is_running = False

    @property
    def timefunc(self):
        if not self._v_timefunc:
            self._v_timefunc = time
        return self._v_timefunc

    @property
    def delayfunc(self):
        if not self._v_delayfunc:
            self._v_delayfunc = sleep
        return self._v_delayfunc

    def add_schedule(self, query, sched, handler):
        self._list.append((SearchSchedule(query, sched), handler))

    def run(self):
        self._v_sched = scheduler(self.timefunc, self.delayfunc)
        for s, handler in self._list:
            query_event(self._v_sched, s, handler)

        def runner():
            self._v_is_running = True
            try:
                self._v_sched.run()
            finally:
                self._v_is_running = False
        self._v_thread = Thread(target=runner)
        self._v_thread.start()

    @property
    def is_running(self):
        if not hasattr(self, '_v_is_running'):
            self._v_is_running = False

        return self._v_is_running

    def stop(self):
        if self._v_sched is None:
            return
        self._v_sched = None
        while not self._v_sched.empty():
            for evt in self._v_sched.queue:
                self._v_sched.cancel(evt)
        self._v_thread.join()


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


SEARCH_TARGETS = {'Arxiv': {'query_type': ArxivQuery},
                  'PubMed': {'query_type': PubmedQuery}}

SEARCH_TARGET_NAMES = list(SEARCH_TARGETS.keys())
AND_OR_COMMA_RGX_STR = r'(\s*,?\s+and\s+|\s*,\s*)'
PLACES_RGX_STR = "({})".format("|".join(re.escape(nom) for nom in SEARCH_TARGET_NAMES))
MSG_RGX_STR = r'''search \s+ for \s+ (?P<query>.*)\s+
                  (on|at) \s+ (?P<targets>{places} ( {and_or_comma} {places})*)
                  (\s+(?P<schedule> .+?))?$'''.format(places=PLACES_RGX_STR,
                                                      and_or_comma=AND_OR_COMMA_RGX_STR)

MSG_RGX = re.compile(MSG_RGX_STR, flags=re.VERBOSE | re.IGNORECASE)

SCHEDULER_KEY = 'search_scheduler'
HANDLER_KEY = 'event_handler'


def get_potential_targets(request):
    return SEARCH_TARGET_NAMES[:]


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
    channel = evt['channel']
    user = evt['user']
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
        query_str = md.group('query')
        # A list of available targets for this requester, a subset of all
        # possible targets (those in the message regex)
        potential_targets = get_potential_targets(request)
        for t in tgts:
            for s in potential_targets:
                if s.lower() == t.lower():
                    found_tgts.append(s)

        queries = []
        for t in found_tgts:
            queries.append(SEARCH_TARGETS[t]['query_type'](query_str))

        user_info = slack_client.api_call('users.info', user=user)
        tz = timezone(user_info['user']['tz'])
        sched = RecurringEvent(now_date=datetime.fromtimestamp(user_ts, tz))
        rrule_str = sched.parse(md.group('schedule'))
        schedule = rrulestr(rrule_str)
        reply = ('OK, <@{}>, I will search for "{}" on {} with a schedule of "{}". '
                 'The next query will be at {}')
        reply = reply.format(user,
                             query_str,
                             ", ".join(found_tgts),
                             str(rrule_str),
                             schedule.after(datetime.now()))

        # TODO: Make this logic also account for per-user schedule requests,
        # org-level event handlers and storage
        key = ('slack_channel', channel)
        if SCHEDULER_KEY not in request.context:
            # TODO: Put this in a different place and use a remote search scheduler
            request.context[SCHEDULER_KEY] = PersistentDict()

        if key not in request.context[SCHEDULER_KEY]:
            request.context[SCHEDULER_KEY][key] = ListSearchScheduler()

        if HANDLER_KEY not in request.context:
            # TODO: Put this in a different place and use a remote event handler
            request.context[HANDLER_KEY] = PersistentDict()

        if key not in request.context[HANDLER_KEY]:
            request.context[HANDLER_KEY][key] = EventHandler()

        scheduler = request.context[SCHEDULER_KEY][key]
        event_handler = request.context[HANDLER_KEY][key]

        for q in queries:
            scheduler.add_schedule(q, schedule, event_handler)

        if not scheduler.is_running:
            scheduler.run()
    else:
        with Popen(["fortune"], stdout=subproc_PIPE) as proc:
            fortune = proc.stdout.read().decode('utf-8')
        reply = 'Sorry, <@{}>, I don\'t know about that, but think about this:\n{}'
        reply = reply.format(user, fortune)

    send_message(slack_client, evt['channel'], reply, thread)
    return Response('')


if __name__ == '__main__':
    with Configurator() as config:
        config.add_route('slack_events', '/events')
        config.add_view(slack_events, route_name='slack_events')
        app = config.make_wsgi_app()

    server = make_server('0.0.0.0', 8080, app)
    server.serve_forever()
