import os
from arxiv_cli import Client as ArxivClient
from slackclient import SlackClient
from urllib.parse import quote_plus as urlquote_plus

api_key = os.environ['SLACK_API_KEY']

sc = SlackClient(api_key)

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


aq = ArxivQuery('ti:C and ti:elegans or abs:C and abs:elegans')
r = aq.execute()

for pe in r.events():
    sc.api_call('chat.postMessage',
                channel='#bot-test',
                text=pe.msg_format(SlackMessageContent).render())
