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
from subprocess import Popen, PIPE as subproc_PIPE
from sched import scheduler
from time import time, sleep
from threading import Thread

from persistent import Persistent
from persistent.list import PersistentList
from persistent.dict import PersistentDict

from logging import Logger

from .persistence_utils import volprop

api_key = os.environ.get('SLACK_API_KEY')

L = Logger(__name__)


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
            link_text = 'ArXiv Query: <http://export.arxiv.org/api/query?search_query={}|{}>'
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

    def execute(self):
        print('running pubmed query for: ' + self.search_query)


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

    def __str__(self):
        return 'New publication "{}" by _{}_ ({})'.format(self.title,
                                                          ', '.join(a.name
                                                                    for a
                                                                    in self.authors),
                                                          self.link)


class ArxivPublicationEvent(PublicationEvent):

    def __init__(self, query, *args, **kwargs):
        super(ArxivPublicationEvent, self).__init__(*args, **kwargs)
        self.query = query

    def msg_format(self, content_type):
        if issubclass(content_type, SlackMessageContent):
            fmt = 'New publication "{}" by _{}_\nMatched by {}'
            msg_str = fmt.format("<{}|{}>".format(self.link, self.title)
                                 if self.link else self.title,
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

    @property
    def start(self):
        return self.sched.dtstart

    @property
    def after(self):
        return self.sched.after


class SearchScheduler(Persistent):
    """ Schedules searches to be performed at regular intervals """

    def add_schedule(self, query, sched, handler):
        """ add a search schedule for the given query """


def query_event(now, scheduler, search_sched, event_handler, priority=0):
    def run():
        response = search_sched.query.execute()
        for evt in response.events():
            event_handler(evt)
        now = datetime.now()
        query_event(now, scheduler, search_sched, event_handler, priority)
    delay = search_sched.after(now, inc=True) - now
    print('delay is', delay)
    scheduler.enter(delay.total_seconds(), priority, run, ())
    return run


class EventHandler(Persistent):
    """ Handles events, yo """

    def __call__(self, event):
        print("Handling event", event)

    def __eq__(self, o):
        return type(self) is type(o)


class SlackMessageEventHandler(EventHandler):
    def __init__(self, channel, requester, **kwargs):
        super(SlackMessageEventHandler, self).__init__(**kwargs)
        self.channel = channel
    slack_api_key = volprop('slack_api_key',
                            lambda: os.environ.get('SLACK_API_KEY'))

    def __call__(self, event):
        mfrag = event.msg_format(SlackMessageContent)
        send_message(self.slack_api_key,
                     self.channel,
                     mfrag.render())


class ListSearchScheduler(SearchScheduler):
    def __init__(self, sched_list=None, **kwargs):
        super(ListSearchScheduler, self).__init__(**kwargs)
        if sched_list is None:
            sched_list = []
        self._list = PersistentList(sched_list)
        self._unhandled_list = PersistentList([])
        self.should_run = True
        self.add_poll_delay = 1 # second

    def __eq__(self, o):
        return self._list == o._list

    timefunc = volprop('timefunc', lambda: time)
    delayfunc = volprop('delayfunc', lambda: sleep)
    sched = volprop('sched')
    thread = volprop('thread')
    is_running = volprop('is_running', lambda: False)

    def add_schedule(self, query, sched, handler):
        search_sched = SearchSchedule(query, sched)
        self._list.append((search_sched, handler))
        self._unhandled_list.append((search_sched, handler))
        # self.send_event(ScheduleAddedEvent(search_sched, handler))

    def run(self):
        self.sched = scheduler(self.timefunc, self.delayfunc)

        for s, handler in self._list:
            query_event(datetime.now(), self.sched, s, handler)

        def handle_adds():
            while len(self._unhandled_list) > 0:
                s, handler = self._unhandled_list.pop(0)
                query_event(s.start, self.sched, s, handler)

            self.sched.enter(self.add_poll_delay, 0, handle_adds, ())

        handle_adds()

        def runner():
            while self.should_run:
                self.is_running = True
                try:
                    self.sched.run()
                except Exception:
                    L.error("Got an exception while running scheduler: ",
                            exc_info=True)
            self.is_running = False
        self.thread = Thread(target=runner)
        self.thread.start()

    def stop(self):
        if self.sched:
            while not self.sched.empty():
                for evt in self.sched.queue:
                    self.sched.cancel(evt)
        if self.thread:
            self.thread.join()


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


def slack_api(request):
    print('API request', request)
    return Response('{}')


def slack_events(request):
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
    print(user_ts)
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

        user_now = datetime.utcfromtimestamp(user_ts)
        sched = RecurringEvent(now_date=user_now)
        sched_str = md.group('schedule')
        if not sched_str:
            sched_str = 'daily'
        rrule_str = sched.parse(sched_str)
        if rrule_str:
            schedule = rrulestr(rrule_str)
            schedule.dtstart = user_now
            reply = ('OK, <@{}>, I will search for "{}" on {} with a schedule of "{}". '
                     'The next query will be at {}')
            reply = reply.format(user,
                                 query_str,
                                 ", ".join(found_tgts),
                                 str(rrule_str),
                                 schedule.after(user_now))

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
                request.context[HANDLER_KEY][key] = SlackMessageEventHandler(channel, user)

            scheduler = request.context[SCHEDULER_KEY][key]
            event_handler = request.context[HANDLER_KEY][key]

            for q in queries:
                scheduler.add_schedule(q, schedule, event_handler)
        else:
            reply = 'Sorry, <@{}>, but I don\'t understand this search schedule: {}'
            reply = reply.format(user, sched_str)
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
