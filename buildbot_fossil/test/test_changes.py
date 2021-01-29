"""Tests for changes.FossilPoller"""

from datetime import datetime, timezone

from buildbot.test.fake import httpclientservice as fakehttpclientservice
from buildbot.test.util.changesource import ChangeSourceMixin
from buildbot.test.util.logging import LoggingMixin
from buildbot.test.util.misc import TestReactorMixin
from buildbot.util import datetime2epoch, httpclientservice
from twisted.internet import defer
from twisted.trial import unittest

from ..changes import FossilPoller

REPOURL = "https://fossil-scm.example/home"


class TestRSSFossilPoller(
    ChangeSourceMixin, LoggingMixin, TestReactorMixin, unittest.TestCase
):
    """Testing the RSS mode of FossilPoller"""

    @defer.inlineCallbacks
    def setUp(self):
        self.setUpTestReactor()
        self.setUpLogging()
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
        self.changesource = FossilPoller(repourl, rss=True, **kwargs)

    @defer.inlineCallbacks
    def start_changesource(self):
        """Start the change source service running"""
        yield self.attachChangeSource(self.changesource)

    @defer.inlineCallbacks
    def test_name(self):
        """
        Name should be equal to repourl so change_hook/poller is easier to use.
        """
        yield self.new_changesource(REPOURL)
        self.assertEqual(REPOURL, self.changesource.name)
        self.assertWasQuiet()

    @defer.inlineCallbacks
    def test_explicit_name(self):
        """
        An explicit name parameter overrides the default.
        """
        yield self.new_changesource(REPOURL, name="my-poller")
        self.assertEqual("my-poller", self.changesource.name)
        self.assertWasQuiet()

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
        self.assertLogged(r"Fossil at nowhere returned code 404")

    @defer.inlineCallbacks
    def test_no_http_service(self):
        """
        If HTTPClientService is not available, we should reject the config.
        """

        def mock_avail(module):
            raise RuntimeError(module)

        self.patch(httpclientservice.HTTPClientService, "checkAvailable", mock_avail)
        with self.assertRaises(RuntimeError):
            yield self.new_changesource(REPOURL)

    RSS = """<?xml version="1.0"?>
        <rss xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0">
          <channel>
            <title>Buildbot-fossil</title>
            <link>http://fossil.local/buildbot-fossil</link>
            <description>Fossil plugin for Buildbot</description>
            <pubDate>Fri, 29 Jan 2021 01:19:34 +0000</pubDate>
            <generator>Fossil version [49f68be83b] 2021-01-02 13:39:46</generator>
            <item>
              <title>Remove the path dependency on buildbot. This prevented the built wheel from working correctly on the server. (tags: trunk)</title>
              <link>http://fossil.local/buildbot-fossil/info/fe7bf77289d5b0097b27692f1567bc45308272cf8e3456d1a26efc033cfadafb</link>
              <description>Remove the path dependency on buildbot. This prevented the built wheel from working correctly on the server. (tags: trunk)</description>
              <pubDate>Mon, 18 Jan 2021 01:05:58 +0000</pubDate>
              <dc:creator>jolesen</dc:creator>
              <guid>http://fossil.local/buildbot-fossil/info/fe7bf77289d5b0097b27692f1567bc45308272cf8e3456d1a26efc033cfadafb</guid>
            </item>
            <item>
              <title>*MERGE* Test logging, merge poetry (tags: trunk)</title>
              <link>http://fossil.local/buildbot-fossil/info/eade2f86c050cf06aca42cc7f1b8bfb9bda586823e0713e6933c736e679cce24</link>
              <description>*MERGE* Test logging, merge poetry (tags: trunk)</description>
              <pubDate>Sun, 10 Jan 2021 18:44:36 +0000</pubDate>
              <dc:creator>jolesen</dc:creator>
              <guid>http://fossil.local/buildbot-fossil/info/eade2f86c050cf06aca42cc7f1b8bfb9bda586823e0713e6933c736e679cce24</guid>
            </item>
          </channel>
        </rss>
    """

    RSS2 = """<?xml version="1.0"?>
        <rss xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0">
          <channel>
            <title>Buildbot-fossil</title>
            <link>http://fossil.local/buildbot-fossil</link>
            <description>Fossil plugin for Buildbot</description>
            <pubDate>Fri, 29 Jan 2021 01:19:34 +0000</pubDate>
            <generator>Fossil version [49f68be83b] 2021-01-02 13:39:46</generator>
            <item>
              <title>*MERGE* Test logging, merge poetry (tags: trunk)</title>
              <link>http://fossil.local/buildbot-fossil/info/eade2f86c050cf06aca42cc7f1b8bfb9bda586823e0713e6933c736e679cce24</link>
              <description>*MERGE* Test logging, merge poetry (tags: trunk)</description>
              <pubDate>Sun, 10 Jan 2021 18:44:36 +0000</pubDate>
              <dc:creator>jolesen</dc:creator>
              <guid>http://fossil.local/buildbot-fossil/info/eade2f86c050cf06aca42cc7f1b8bfb9bda586823e0713e6933c736e679cce24</guid>
            </item>
            <item>
              <title>*FORK* Test for missing HTTP service (tags: trunk)</title>
              <link>http://fossil.local/buildbot-fossil/info/fdd7d7dcde7a8fea1c50728e511973f630b04daee0297bbeb70a7fb494e44f21</link>
              <description>*FORK* Test for missing HTTP service (tags: trunk)</description>
              <pubDate>Sat, 9 Jan 2021 01:41:38 +0000</pubDate>
              <dc:creator>jolesen</dc:creator>
              <guid>http://fossil.local/buildbot-fossil/info/fdd7d7dcde7a8fea1c50728e511973f630b04daee0297bbeb70a7fb494e44f21</guid>
            </item>
          </channel>
        </rss>
    """

    @defer.inlineCallbacks
    def test_rss(self):
        """
        Check that we can extract change entries from an RSS feed.
        """
        yield self.new_changesource(REPOURL)
        self.http.expect("get", "/timeline.rss", params={"y": "ci"}, content=self.RSS)
        yield self.start_changesource()

        self.assertEqual(len(self.master.data.updates.changesAdded), 2)

        # Changes should appear in chronological order.
        chdict = self.master.data.updates.changesAdded[0]
        self.assertEqual(chdict["author"], "jolesen")
        self.assertEqual(
            chdict["revision"],
            "eade2f86c050cf06aca42cc7f1b8bfb9bda586823e0713e6933c736e679cce24",
        )
        self.assertEqual(
            chdict["revlink"],
            "http://fossil.local/buildbot-fossil/info/"
            "eade2f86c050cf06aca42cc7f1b8bfb9bda586823e0713e6933c736e679cce24",
        )
        self.assertEqual(chdict["branch"], "trunk")
        self.assertEqual(chdict["repository"], REPOURL)
        # RSS doesn't provide list of changes files.
        self.assertIsNone(chdict["files"])
        self.assertEqual(chdict["comments"], "*MERGE* Test logging, merge poetry")
        self.assertEqual(
            chdict["when_timestamp"],
            datetime2epoch(datetime(2021, 1, 10, 18, 44, 36, tzinfo=timezone.utc)),
        )

        chdict = self.master.data.updates.changesAdded[1]
        self.assertEqual(
            chdict["revision"],
            "fe7bf77289d5b0097b27692f1567bc45308272cf8e3456d1a26efc033cfadafb",
        )
        self.assertEqual(
            chdict["comments"],
            "Remove the path dependency on buildbot. "
            "This prevented the built wheel from working correctly on the server.",
        )

        # The change source should save a list of seen revisions.
        self.master.db.state.assertStateByClass(
            name=REPOURL,
            class_name="FossilPoller",
            last_fetch=[
                "eade2f86c050cf06aca42cc7f1b8bfb9bda586823e0713e6933c736e679cce24",
                "fe7bf77289d5b0097b27692f1567bc45308272cf8e3456d1a26efc033cfadafb",
            ],
        )

    @defer.inlineCallbacks
    def test_repeat_filter(self):
        """
        Test that duplicates are filtered out.
        """
        yield self.new_changesource(REPOURL)
        self.http.expect("get", "/timeline.rss", params={"y": "ci"}, content=self.RSS)
        self.http.expect("get", "/timeline.rss", params={"y": "ci"}, content=self.RSS2)
        yield self.start_changesource()
        yield self.changesource.poll()
        # The two feeds have one item in common.
        self.assertEqual(len(self.master.data.updates.changesAdded), 3)

        # Don't accumulate revisions, just save the ones from the last fetch (RSS2).
        self.master.db.state.assertStateByClass(
            name=REPOURL,
            class_name="FossilPoller",
            last_fetch=[
                "fdd7d7dcde7a8fea1c50728e511973f630b04daee0297bbeb70a7fb494e44f21",
                "eade2f86c050cf06aca42cc7f1b8bfb9bda586823e0713e6933c736e679cce24",
            ],
        )

    @defer.inlineCallbacks
    def test_saved_repeat_filter(self):
        """
        Test that the fetched revisions are saved across restarts.
        """
        self.master.db.state.fakeState(
            name=REPOURL,
            class_name="FossilPoller",
            last_fetch=[
                "eade2f86c050cf06aca42cc7f1b8bfb9bda586823e0713e6933c736e679cce24",
            ],
        )

        yield self.new_changesource(REPOURL)
        self.http.expect("get", "/timeline.rss", params={"y": "ci"}, content=self.RSS)
        yield self.start_changesource()

        self.assertEqual(len(self.master.data.updates.changesAdded), 1)
        chdict = self.master.data.updates.changesAdded[0]
        self.assertEqual(
            chdict["revision"],
            "fe7bf77289d5b0097b27692f1567bc45308272cf8e3456d1a26efc033cfadafb",
        )
