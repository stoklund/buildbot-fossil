from twisted.internet import defer
from twisted.trial import unittest

from ..changes import FossilPoller

from buildbot.test.fake import httpclientservice as fakehttpclientservice
from buildbot.test.util.misc import TestReactorMixin
from buildbot.test.util.changesource import ChangeSourceMixin


class TestRSSFossilPoller(
        ChangeSourceMixin, TestReactorMixin, unittest.TestCase):

    @defer.inlineCallbacks
    def setUp(self):
        self.setUpTestReactor()
        yield self.setUpChangeSource()
        yield self.master.startService()

    @defer.inlineCallbacks
    def tearDown(self):
        yield self.master.stopService()
        yield self.tearDownChangeSource()

    @defer.inlineCallbacks
    def newChangeSource(self, repourl, **kwargs):
        '''
        Create a new fake HTTP service and change source. Don't start them yet.
        '''
        http_headers = {'User-Agent': 'Buildbot'}
        self.http = yield fakehttpclientservice.HTTPClientService.getService(
            self.master, self, repourl, headers=http_headers)
        self.changesource = FossilPoller(repourl, **kwargs)

    @defer.inlineCallbacks
    def startChangeSource(self):
        yield self.attachChangeSource(self.changesource)

    @defer.inlineCallbacks
    def test_name(self):
        url = 'https://fossil-scm.org/home'
        yield self.newChangeSource(url)
        # Name should be equal to repourl so change_hook/poller is easier.
        self.assertEqual(url, self.changesource.name)

    @defer.inlineCallbacks
    def test_describe(self):
        yield self.newChangeSource('nowhere')
        self.http.expect('get', '/timeline.rss', params={'y': 'ci'}, code=404)
        yield self.startChangeSource()
        self.assertEqual("FossilPoller watching 'nowhere'",
                         self.changesource.describe())
