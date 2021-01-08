from twisted.internet import defer

from buildbot import config
from buildbot.changes import base
from buildbot.util import datetime2epoch
from buildbot.util.httpclientservice import HTTPClientService
from buildbot.util.logger import Logger
from buildbot.util.state import StateMixin

from datetime import datetime
import re
import xml.etree.ElementTree as ET

log = Logger()


class FossilPoller(base.ReconfigurablePollingChangeSource, StateMixin):

    """This source will poll a remote fossil repo for changes and submit
    them to the change master."""

    compare_attrs = ("repourl",
                     "pollInterval", "pollAtLaunch",
                     "pollRandomDelayMin", "pollRandomDelayMax")

    db_class_name = 'FossilPoller'

    def __init__(self, repourl,
                 name=None,
                 pollInterval=10 * 60,
                 pollAtLaunch=True,
                 pollRandomDelayMin=0,
                 pollRandomDelayMax=0):
        '''Create a Fossil SCM poller.'''
        if name is None:
            name = repourl

        super().__init__(repourl,
                         name=name,
                         pollInterval=pollInterval,
                         pollAtLaunch=pollAtLaunch,
                         pollRandomDelayMin=pollRandomDelayMin,
                         pollRandomDelayMax=pollRandomDelayMax)

        self.repourl = repourl
        self.lastFetch = set()

    def checkConfig(self, repourl, **kwargs):
        if repourl.endswith('/'):
            config.error('repourl must not end in /')
        HTTPClientService.checkAvailable(self.__class__.__name__)
        super().checkConfig(repourl, **kwargs)

    @defer.inlineCallbacks
    def reconfigService(self, repourl, **kwargs):
        yield super().reconfigService(**kwargs)
        self.repourl = repourl

        http_headers = {'User-Agent': 'Buildbot'}
        self._http = yield HTTPClientService.getService(
            self.master, repourl, headers=http_headers)

    @defer.inlineCallbacks
    def activate(self):
        try:
            lastFetch = yield self.getState('lastFetch', [])
            self.lastFetch = set(lastFetch)
            super().activate()
        except Exception:
            log.failure('while initializing FossilPoller repository')

    def describe(self):
        status = ""
        if not self.master:
            status = " [STOPPED - check log]"
        return f"FossilPoller watching '{self.repourl}'{status}"

    @defer.inlineCallbacks
    def poll(self):
        changes = yield self._fetchRSS()
        yield self._processChanges(changes)

    @defer.inlineCallbacks
    def _fetchRSS(self):
        # The fossil /timeline.rss entry point takes these query parameters:
        # - y=ci selects checkins only.
        # - n=10 limits the number of entries returned.
        # - tag=foo selects a single branch
        params = dict(y='ci')

        response = yield self._http.get('/timeline.rss', params=params)
        if response.code != 200:
            log.error("Fossil {url} returned code "
                      "{response.code} {response.phrase}",
                      url=self.repourl, response=response)
            return []

        xml = yield response.content()
        etree = ET.fromstring(xml)
        ns = dict(dc="http://purl.org/dc/elements/1.1/")
        project = etree.findtext('channel/title')

        changes = list()
        for node in etree.findall('channel/item'):
            title = node.findtext('title')
            link = node.findtext('link')
            date = node.findtext('pubDate')
            creator = node.findtext('dc:creator', namespaces=ns)

            ch = dict(
                revlink=link,
                author=creator,
                repository=self.repourl,
                project=project)
            changes.append(ch)

            # Extract tags from the title.
            m = re.match(r'(.*) \(tags: ([^()]*)\)$', title)
            if m:
                ch['comments'] = m[1]
                tags = m[2].split(', ')
                ch['branch'] = tags[0]
            else:
                ch['comments'] = title
                tags = []

            # The commit hash is the last part of the link URL.
            ch['revision'] = link.rsplit('/', 1)[-1]

            # Date format: Sat, 26 Dec 2020 00:00:42 +0000
            dt = datetime.strptime(date, '%a, %d %b %Y %H:%M:%S %z')
            ch['when_timestamp'] = datetime2epoch(dt)

        # Changes appear from newest to oldest in the RSS feed.
        changes.reverse()
        return changes

    @defer.inlineCallbacks
    def _processChanges(self, changes):
        fetched = set()
        for ch in changes:
            rev = ch['revision']
            fetched.add(rev)
            if rev not in self.lastFetch:
                # The `src` argument is used to create user objects.
                # Since buildbot doesn't know about fossil, we pass 'svn'
                # which has similar user names.
                yield self.master.data.updates.addChange(src='svn', **ch)

        self.lastFetch = fetched
        yield self.setState('lastFetch', list(fetched))
