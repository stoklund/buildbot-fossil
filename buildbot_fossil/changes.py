"""Polling Fossil for source changes"""

import re
import xml.etree.ElementTree as ET
from datetime import datetime

from buildbot import config
from buildbot.changes import base
from buildbot.util import datetime2epoch
from buildbot.util.httpclientservice import HTTPClientService
from buildbot.util.logger import Logger
from buildbot.util.state import StateMixin
from twisted.internet import defer

log = Logger()
XMLNS_MAP = dict(dc="http://purl.org/dc/elements/1.1/")


class FossilPoller(base.ReconfigurablePollingChangeSource, StateMixin):

    """This source will poll a remote fossil repo for changes and submit
    them to the change master."""

    compare_attrs = (
        "repourl",
        "rss",
        "pollInterval",
        "pollAtLaunch",
        "pollRandomDelayMin",
        "pollRandomDelayMax",
    )

    db_class_name = "FossilPoller"

    def __init__(
        self,
        repourl,
        rss=False,
        name=None,
        pollInterval=10 * 60,
        pollAtLaunch=True,
        pollRandomDelayMin=0,
        pollRandomDelayMax=0,
    ):
        """Create a Fossil SCM poller."""
        if name is None:
            name = repourl

        super().__init__(
            repourl,
            rss=rss,
            name=name,
            pollInterval=pollInterval,
            pollAtLaunch=pollAtLaunch,
            pollRandomDelayMin=pollRandomDelayMin,
            pollRandomDelayMax=pollRandomDelayMax,
        )

        self.repourl = repourl
        self.rss = rss

        self.last_fetch = set()
        self._http = None  # Set in reconfigService()

    # pylint: disable=arguments-differ
    def checkConfig(self, repourl, rss=False, **kwargs):
        if repourl.endswith("/"):
            config.error("repourl must not end in /")
        if not rss in (True, False):
            config.error("The `rss` parameter must be True or False")

        HTTPClientService.checkAvailable(self.__class__.__name__)

        super().checkConfig(repourl, **kwargs)

    # pylint: disable=arguments-differ
    @defer.inlineCallbacks
    def reconfigService(self, repourl, rss=False, **kwargs):
        yield super().reconfigService(**kwargs)
        self.repourl = repourl
        self.rss = rss

        http_headers = {"User-Agent": "Buildbot"}
        self._http = yield HTTPClientService.getService(
            self.master, repourl, headers=http_headers
        )

    @defer.inlineCallbacks
    def activate(self):
        try:
            last_fetch = yield self.getState("last_fetch", [])
            self.last_fetch = set(last_fetch)
            super().activate()
        except Exception:
            log.failure("while initializing FossilPoller repository")

    def describe(self):
        status = ""
        if not self.master:
            status = " [STOPPED - check log]"
        return f"FossilPoller watching '{self.repourl}'{status}"

    @defer.inlineCallbacks
    def poll(self):
        if not self.rss:
            changes = yield self._fetch_json()
        else:
            changes = yield self._fetch_rss()
        yield self._process_changes(changes)

    @defer.inlineCallbacks
    def _fetch_json(self):
        # The /json/timeline/checkin API takes the following parameters:
        # - files=bool enables the `files` list.
        # - tag|branch=string only sends checkins for a specific branch.
        # See https://fossil-scm.org/home/doc/trunk/www/json-api/api-timeline.md
        payload = yield self._json_get("timeline/checkin", files=True)

        changes = list()
        for entry in reversed(payload["timeline"]):
            chdict = dict(
                author=entry["user"],
                comments=entry["comment"],
                revision=entry["uuid"],
                when_timestamp=entry["timestamp"],
                revlink=f"{self.repourl}/info/{entry['uuid']}",
                repository=self.repourl,
            )
            changes.append(chdict)

            if "files" in entry:
                chdict["files"] = [d["name"] for d in entry["files"]]

            tags = entry["tags"]
            if tags:
                chdict["branch"] = tags[0]

        return changes

    @defer.inlineCallbacks
    def _json_get(self, endpoint, **kwargs):
        """
        Make a JSON GET request to /json/{endpoint}.

        Returns the returned payload as a dict.
        """
        response = yield self._http.get("/json/" + endpoint, params=kwargs)
        if response.code != 200:
            log.error(
                "JSON request to {url}/json/{endpoint} returned "
                "HTTP status {response.code}",
                url=self.repourl,
                endpoint=endpoint,
                response=response,
            )
            raise RuntimeError(f"HTTP {response.code} from {self.repourl}/json")

        # Decode the JSON response envelope.
        renv = yield response.json()
        if "fossil" not in renv:
            raise RuntimeError("JSON response is not from a Fossil server", renv)

        # resultCode is only set for errors.
        resultCode = str(renv.get("resultCode", ""))
        if resultCode:
            if resultCode.startswith("FOSSIL-"):
                return resultCode
            raise RuntimeError(f"Invalid resultCode '{resultCode}'")

        payload = renv.get("payload", {})
        if not isinstance(payload, dict):
            raise RuntimeError(f"Expected dict payload: '{payload}'")

        return payload

    @defer.inlineCallbacks
    def _fetch_rss(self):
        # The fossil /timeline.rss entry point takes these query parameters:
        # - y=ci selects checkins only.
        # - n=10 limits the number of entries returned.
        # - tag=foo selects a single branch
        params = dict(y="ci")

        response = yield self._http.get("/timeline.rss", params=params)
        if response.code != 200:
            log.error(
                "Fossil at {url} returned code {response.code}",
                url=self.repourl,
                response=response,
            )
            return []

        xml = yield response.content()
        etree = ET.fromstring(xml)
        project = etree.findtext("channel/title")

        changes = list()
        for node in etree.findall("channel/item"):
            ch_dict = dict(
                revlink=node.findtext("link"),
                author=node.findtext("dc:creator", namespaces=XMLNS_MAP),
                repository=self.repourl,
                project=project,
            )
            changes.append(ch_dict)

            # Extract tags from the title.
            title = node.findtext("title")
            match = re.match(r"(.*) \(tags: ([^()]*)\)$", title)
            if match:
                ch_dict["comments"] = match[1]
                tags = match[2].split(", ")
                ch_dict["branch"] = tags[0]
            else:
                ch_dict["comments"] = title
                tags = []

            # The commit hash is the last part of the link URL.
            ch_dict["revision"] = ch_dict["revlink"].rsplit("/", 1)[-1]

            # Date format: Sat, 26 Dec 2020 00:00:42 +0000
            ch_dict["when_timestamp"] = datetime2epoch(
                datetime.strptime(node.findtext("pubDate"), "%a, %d %b %Y %H:%M:%S %z")
            )

        # Changes appear from newest to oldest in the RSS feed.
        changes.reverse()
        return changes

    @defer.inlineCallbacks
    def _process_changes(self, changes):
        fetched = list()
        for ch_dict in changes:
            rev = ch_dict["revision"]
            fetched.append(rev)
            if rev not in self.last_fetch:
                # The `src` argument is used to create user objects.
                # Since buildbot doesn't know about fossil, we pass 'svn'
                # which has similar user names.
                yield self.master.data.updates.addChange(src="svn", **ch_dict)

        self.last_fetch = set(fetched)
        yield self.setState("last_fetch", fetched)
