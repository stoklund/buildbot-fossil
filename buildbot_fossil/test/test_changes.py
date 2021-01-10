"""Tests for changes.FossilPoller"""

from twisted.internet import defer
from twisted.trial import unittest

from buildbot.util import httpclientservice
from buildbot.test.fake import httpclientservice as fakehttpclientservice
from buildbot.test.util.misc import TestReactorMixin
from buildbot.test.util.changesource import ChangeSourceMixin

from ..changes import FossilPoller


class TestRSSFossilPoller(ChangeSourceMixin, TestReactorMixin, unittest.TestCase):
    """Testing the RSS mode of FossilPoller"""

    REPOURL = "https://fossil-scm.example/home"

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
    def new_changesource(self, repourl, **kwargs):
        """
        Create a new fake HTTP service and change source. Don't start them yet.
        """
        # pylint: disable=attribute-defined-outside-init
        http_headers = {"User-Agent": "Buildbot"}
        self.http = yield fakehttpclientservice.HTTPClientService.getService(
            self.master, self, repourl, headers=http_headers
        )
        self.changesource = FossilPoller(repourl, **kwargs)

    @defer.inlineCallbacks
    def start_changesource(self):
        """Start the change source service running"""
        yield self.attachChangeSource(self.changesource)

    @defer.inlineCallbacks
    def test_name(self):
        """
        Name should be equal to repourl so change_hook/poller is easier to use.
        """
        yield self.new_changesource(self.REPOURL)
        self.assertEqual(self.REPOURL, self.changesource.name)

    @defer.inlineCallbacks
    def test_explicit_name(self):
        """
        An explicit name parameter overrides the default.
        """
        yield self.new_changesource(self.REPOURL, name="my-poller")
        self.assertEqual("my-poller", self.changesource.name)

    @defer.inlineCallbacks
    def test_describe(self):
        """
        The describe() method can provide more info
        """
        yield self.new_changesource("nowhere")
        self.assertEqual(
            "FossilPoller watching 'nowhere' [STOPPED - check log]",
            self.changesource.describe(),
        )
        self.http.expect("get", "/timeline.rss", params={"y": "ci"}, code=404)
        yield self.start_changesource()
        self.assertEqual(
            "FossilPoller watching 'nowhere'", self.changesource.describe()
        )

    @defer.inlineCallbacks
    def test_no_http_service(self):
        """
        If HTTPClientService is not available, we should reject the config.
        """

        def mock_avail(module):
            raise RuntimeError(module)

        self.patch(httpclientservice.HTTPClientService, "checkAvailable", mock_avail)
        with self.assertRaises(RuntimeError):
            yield self.new_changesource(self.REPOURL)
