from pyramid.config import Configurator
from pyramid_zodbconn import get_connection
from .models import appmaker
from .slack_bot import slack_events, slack_api, SCHEDULER_KEY
from zodburi import resolve_uri
from ZODB.DB import DB
import transaction


def root_factory(request):
    conn = get_connection(request)
    return appmaker(conn.root())


def make_init_db(uri):
    storage_factory, dbkw = resolve_uri(uri)
    storage = storage_factory()
    db = DB(storage, **dbkw)
    return db


class SchedulerData(object):
    def __init__(self):
        self.connection = None
        self.scheduler = None
        self.database = None


def run_schedulers(uri, conn):
    sdata = []
    try:
        root = appmaker(conn.root())
        schedulers = root.get(SCHEDULER_KEY)
        if schedulers:
            print("we have schedulers")
            for oid in (x._p_oid for x in schedulers.values()):
                sd = SchedulerData()
                sd.database = make_init_db(uri)
                sd.connection = sd.database.open()
                sd.scheduler = sd.connection.get(oid)
                sd.scheduler.run()
                sdata.append(sd)
        else:
            print("we have no schedulers")
    finally:
        transaction.commit()
        return sdata


def main(global_config, **settings):
    """ This function returns a Pyramid WSGI application.
    """
    settings['tm.manager_hook'] = 'pyramid_tm.explicit_manager'
    uri = settings['zodbconn.uri']
    db = make_init_db(uri)
    conn = db.open()
    try:
        run_schedulers(uri, conn)
    finally:
        conn.close()
        db.close()

    with Configurator(settings=settings) as config:
        config.include('pyramid_jinja2')
        config.add_jinja2_renderer('.j2', settings_prefix='jinja2.')
        config.include('pyramid_tm')
        config.include('pyramid_retry')
        config.include('pyramid_zodbconn')
        config.set_root_factory(root_factory)
        config.add_static_view('static', 'static', cache_max_age=3600)
        config.add_route('slack_events', '/events')
        config.add_route('slack_api', '/api')
        config.add_view(slack_events, route_name='slack_events')
        config.add_view(slack_api, route_name='slack_api')
        return config.make_wsgi_app()
