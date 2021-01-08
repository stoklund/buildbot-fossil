"""Tests for changes.FossilPoller"""

from twisted.internet import defer
from twisted.trial import unittest

from buildbot.test.fake import httpclientservice as fakehttpclientservice
from buildbot.test.util.misc import TestReactorMixin
from buildbot.test.util.changesource import ChangeSourceMixin

from ..changes import FossilPoller


class TestRSSFossilPoller(
        ChangeSourceMixin, TestReactorMixin, unittest.TestCase):
    """Testing the RSS mode of FossilPoller"""

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
    def new_change_source(self, repourl, **kwargs):
        '''
        Create a new fake HTTP service and change source. Don't start them yet.
        '''
        # pylint: disable=attribute-defined-outside-init
        http_headers = {'User-Agent': 'Buildbot'}
        self.http = yield fakehttpclientservice.HTTPClientService.getService(
            self.master, self, repourl, headers=http_headers)
        self.changesource = FossilPoller(repourl, **kwargs)

    @defer.inlineCallbacks
    def startChangeSource(self):
        yield self.attachChangeSource(self.changesource)

    @defer.inlineCallbacks
    def test_name(self):
        """
        Name should be equal to repourl so change_hook/poller is easier to use.
        """
        url = 'https://fossil-scm.org/home'
        yield self.new_change_source(url)
        self.assertEqual(url, self.changesource.name)

    @defer.inlineCallbacks
    def test_describe(self):
        """
        The describe() method can provide more info
        """
        yield self.new_change_source('nowhere')
        self.http.expect('get', '/timeline.rss', params={'y': 'ci'}, code=404)
        yield self.startChangeSource()
        self.assertEqual("FossilPoller watching 'nowhere'",
                         self.changesource.describe())
