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
        Create a new fake HTTP service and change source and start them.
        """
        # pylint: disable=attribute-defined-outside-init
        http_headers = {"User-Agent": "Buildbot"}
        self.http = yield fakehttpclientservice.HTTPClientService.getService(
            self.master, self, repourl, headers=http_headers
        )
        self.changesource = FossilPoller(repourl, rss=True, **kwargs)
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
            "FossilPoller watching 'nowhere'",
            self.changesource.describe(),
        )
        self.http.expect("get", "/timeline.rss", params={"y": "ci"}, code=404)
        yield self.changesource.poll()
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

    # pylint: disable=line-too-long
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

    # pylint: disable=line-too-long
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
        yield self.changesource.poll()

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
        yield self.changesource.poll()
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
        yield self.changesource.poll()

        self.assertEqual(len(self.master.data.updates.changesAdded), 1)
        chdict = self.master.data.updates.changesAdded[0]
        self.assertEqual(
            chdict["revision"],
            "fe7bf77289d5b0097b27692f1567bc45308272cf8e3456d1a26efc033cfadafb",
        )


class TestJSONFossilPoller(
    ChangeSourceMixin, LoggingMixin, TestReactorMixin, unittest.TestCase
):
    """Testing the JSON mode of FossilPoller"""

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
        Create a new fake HTTP service and change source and start them.
        """
        # pylint: disable=attribute-defined-outside-init
        http_headers = {"User-Agent": "Buildbot"}
        self.http = yield fakehttpclientservice.HTTPClientService.getService(
            self.master, self, repourl, headers=http_headers
        )
        self.changesource = FossilPoller(repourl, **kwargs)
        yield self.attachChangeSource(self.changesource)

    # pylint: disable=line-too-long
    JSON = {
        "fossil": "a54732919d8ed1ba3adf0b5032f430da8a0c8883dcdb1affe1666613a236463b",
        "timestamp": 1611945181,
        "command": "timeline/checkin",
        "procTimeUs": 4309,
        "procTimeMs": 4,
        "payload": {
            "limit": 2,
            "timeline": [
                {
                    "type": "checkin",
                    "uuid": "c4da1011eed6e7ac8c84f7bbd4f23c80af4638bc230da1926587f01381713316",
                    "isLeaf": True,
                    "timestamp": 1611943432,
                    "user": "jolesen",
                    "comment": "Add an 'rss' flag for enabling RSS mode. Default to JSON which isn't implemented yet.",
                    "parents": [
                        "4ccf5d57ec51f0ffde0d1208ba22fe6b8ce1296657763c316f95123d433fe94c"
                    ],
                    "tags": ["trunk"],
                    "files": [
                        {
                            "name": "buildbot_fossil/changes.py",
                            "uuid": "668d8aeb0efab259f1bac662402ee94405e2fef51b472eb9ad841ec8233aa60e",
                            "parent": "5f9399bf08f7c40fda319b3b7d48cb0ed8512eded25200f1f5c5a891c2347705",
                            "size": 5523,
                            "state": "modified",
                            "downloadPath": "/raw/buildbot_fossil/changes.py?name=668d8aeb0efab259f1bac662402ee94405e2fef51b472eb9ad841ec8233aa60e",
                        },
                        {
                            "name": "buildbot_fossil/test/test_changes.py",
                            "uuid": "5993611a1e377b1941d717ce549b17b51186353ac3ec7328a5c5c97837a83442",
                            "parent": "d4247070e0d0e4d298f7bcc2767f653d603491a00fe8f2c937e6b9b8499efa56",
                            "size": 10774,
                            "state": "modified",
                            "downloadPath": "/raw/buildbot_fossil/test/test_changes.py?name=5993611a1e377b1941d717ce549b17b51186353ac3ec7328a5c5c97837a83442",
                        },
                    ],
                },
                {
                    "type": "checkin",
                    "uuid": "4ccf5d57ec51f0ffde0d1208ba22fe6b8ce1296657763c316f95123d433fe94c",
                    "isLeaf": False,
                    "timestamp": 1611942417,
                    "user": "jolesen",
                    "comment": "Test the filter for repeated revisions. Make the saved list order consistent.",
                    "parents": [
                        "f69a18de8a19ace4cc45bc1dbd6baffbad65837be909c0fcb151c0387b608712"
                    ],
                    "tags": ["trunk"],
                    "files": [
                        {
                            "name": "buildbot_fossil/changes.py",
                            "uuid": "5f9399bf08f7c40fda319b3b7d48cb0ed8512eded25200f1f5c5a891c2347705",
                            "parent": "c11586d95a7b73882af76317cd6b2fbd084d3701637f3424e8ef79863c6b5934",
                            "size": 5330,
                            "state": "modified",
                            "downloadPath": "/raw/buildbot_fossil/changes.py?name=5f9399bf08f7c40fda319b3b7d48cb0ed8512eded25200f1f5c5a891c2347705",
                        },
                        {
                            "name": "buildbot_fossil/test/test_changes.py",
                            "uuid": "d4247070e0d0e4d298f7bcc2767f653d603491a00fe8f2c937e6b9b8499efa56",
                            "parent": "1439c07f47de768d7e42ab023f997ee4d57e4d3f634dee51be753db597f7fa9b",
                            "size": 10823,
                            "state": "modified",
                            "downloadPath": "/raw/buildbot_fossil/test/test_changes.py?name=d4247070e0d0e4d298f7bcc2767f653d603491a00fe8f2c937e6b9b8499efa56",
                        },
                    ],
                },
            ],
        },
    }

    @defer.inlineCallbacks
    def test_json(self):
        """
        Check a simple JSON fetch, assuming we're already logged in.
        """
        yield self.new_changesource(REPOURL)
        self.http.expect(
            "get",
            "/json/timeline/checkin",
            params={"files": True},
            content_json=self.JSON,
        )
        yield self.changesource.poll()

        self.assertEqual(len(self.master.data.updates.changesAdded), 2)

        # Changes should appear in chronological order.
        chdict = self.master.data.updates.changesAdded[0]
        rev = "4ccf5d57ec51f0ffde0d1208ba22fe6b8ce1296657763c316f95123d433fe94c"
        self.assertEqual(chdict["author"], "jolesen")
        self.assertEqual(chdict["revision"], rev)
        self.assertEqual(chdict["revlink"], f"{REPOURL}/info/{rev}")
        self.assertEqual(chdict["branch"], "trunk")
        self.assertEqual(chdict["repository"], REPOURL)
        self.assertEqual(
            chdict["files"],
            ["buildbot_fossil/changes.py", "buildbot_fossil/test/test_changes.py"],
        )
        self.assertEqual(
            chdict["comments"],
            "Test the filter for repeated revisions. Make the saved list order consistent.",
        )
        self.assertEqual(chdict["when_timestamp"], 1611942417)

        chdict = self.master.data.updates.changesAdded[1]
        self.assertEqual(
            chdict["revision"],
            "c4da1011eed6e7ac8c84f7bbd4f23c80af4638bc230da1926587f01381713316",
        )

    @defer.inlineCallbacks
    def test_no_json_configured(self):
        """
        A fossil server that hasn't been configured with JSON will return HTTP 404.
        """
        yield self.new_changesource(REPOURL)
        self.http.expect(
            "get", "/json/timeline/checkin", params={"files": True}, code=404
        )
        yield self.changesource.poll()
        self.assertLogged(f"HTTPStatus.NOT_FOUND {REPOURL}/json/timeline/checkin")

    JSON_ERROR = {
        "fossil": "49f68be83be7de1a7af16edd3dc7c5950fc1be3e764227f1dec33f9862650e42",
        "timestamp": 1611972492,
        "resultCode": "FOSSIL-3002",
        "resultText": "No subcommand specified.",
        "command": "timeline",
        "procTimeUs": 2761,
        "procTimeMs": 2,
    }

    @defer.inlineCallbacks
    def test_json_error(self):
        """
        Check handling of some unexpected JSON API error.
        """
        yield self.new_changesource(REPOURL)
        self.http.expect(
            "get",
            "/json/timeline/checkin",
            params={"files": True},
            content_json=self.JSON_ERROR,
        )
        yield self.changesource.poll()
        self.assertLogged("JSONError: FOSSIL-3002: No subcommand specified.")

    JSON_DENIED = {
        "fossil": "49f68be83be7de1a7af16edd3dc7c5950fc1be3e764227f1dec33f9862650e42",
        "timestamp": 1611972492,
        "resultCode": "FOSSIL-2002",
        "resultText": "Check-in timeline requires 'h' access.",
        "command": "timeline/checkin",
        "procTimeUs": 2761,
        "procTimeMs": 2,
    }

    JSON_ANON_PASSWD = {
        "fossil": "49f68be83be7de1a7af16edd3dc7c5950fc1be3e764227f1dec33f9862650e42",
        "timestamp": 1611982240,
        "command": "anonymousPassword",
        "procTimeUs": 3247,
        "procTimeMs": 3,
        "payload": {"seed": 1247781448, "password": "8XXXX13b"},
    }

    JSON_ANON_OK = {
        "fossil": "49f68be83be7de1a7af16edd3dc7c5950fc1be3e764227f1dec33f9862650e42",
        "timestamp": 1611982679,
        "command": "login",
        "procTimeUs": 3177,
        "procTimeMs": 3,
        "payload": {
            "authToken": "b7ef6649d551b44b04d4d3ababc/2459244.7069349/anonymous",
            "name": "anonymous",
            "capabilities": "hmnc",
            "loginCookieName": "fossil-42b934f2ab",
        },
    }

    @defer.inlineCallbacks
    def test_json_anonymous_auth(self):
        """
        Check that the poller will login as anonymous.
        """
        yield self.new_changesource(REPOURL)
        self.http.expect(
            "get",
            "/json/timeline/checkin",
            params={"files": True},
            content_json=self.JSON_DENIED,
        )
        # After a request with auth denied, get the anonymous password.
        self.http.expect(
            "get",
            "/json/anonymousPassword",
            params={},
            content_json=self.JSON_ANON_PASSWD,
        )
        # POST login so passwords don't show up in server logs.
        self.http.expect(
            "post",
            "/json/login",
            json={
                "payload": {
                    "name": "anonymous",
                    "password": "8XXXX13b",
                    "anonymousSeed": 1247781448,
                }
            },
            content_json=self.JSON_ANON_OK,
        )
        self.http.expect(
            "get",
            "/json/timeline/checkin",
            params={"files": True},
            content_json=self.JSON,
        )

        yield self.changesource.poll()
        self.assertLogged(
            "JSONAuthError: FOSSIL-2002: Check-in timeline requires 'h' access"
        )
        self.assertLogged(f"Getting anonymous passsword for {REPOURL}")
        self.assertLogged("Logged in as anonymous")

        cookie = (
            "fossil-42b934f2ab=b7ef6649d551b44b04d4d3ababc/2459244.7069349/anonymous"
        )

        # The login cookie should be saved.
        self.master.db.state.assertStateByClass(
            name=REPOURL, class_name="FossilPoller", login_cookie=cookie
        )
