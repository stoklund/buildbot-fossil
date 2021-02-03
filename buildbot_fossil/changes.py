"""Polling Fossil for source changes"""

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from http import HTTPStatus
from typing import Optional

from buildbot import config
from buildbot.changes import base
from buildbot.util import datetime2epoch
from buildbot.util.httpclientservice import HTTPClientService
from buildbot.util.logger import Logger
from buildbot.util.state import StateMixin
from twisted.internet import defer

log = Logger()
XMLNS_MAP = dict(dc="http://purl.org/dc/elements/1.1/")


class HTTPError(Exception):
    """HTTP-level error."""

    def __init__(self, url, response):
        self.url = url
        self.response = response
        self.status = HTTPStatus(response.code)
        super().__init__()

    def __str__(self):
        return f"{self.status!s} {self.url}"


class JSONError(Exception):
    """JSON API error."""

    def __init__(self, url, envelope):
        self.url = url
        self.envelope = envelope
        super().__init__()

    def __str__(self):
        code = self.envelope["resultCode"]
        text = self.envelope.get("resultText", "")
        return f"{type(self).__name__}: {code}: {text} (from {self.url})"


class JSONAuthError(JSONError):
    """JSON API authentication errors."""


@defer.inlineCallbacks
def json_payload(url, response):
    """
    Extract the payload from a JSON HTTP response.

    Raise exceptions on errors.
    """
    # JSON API errors still return 200, so this is something else.
    if response.code != HTTPStatus.OK:
        raise HTTPError(url, response)

    # Decode the JSON response envelope.
    renv = yield response.json()
    if "fossil" not in renv:
        raise RuntimeError("JSON response is not from a Fossil server", renv)

    # resultCode is only set for errors.
    code = renv.get("resultCode", "")
    if code:
        # Separate authentication errors so we can login again.
        if code.startswith("FOSSIL-2"):
            raise JSONAuthError(url, renv)
        raise JSONError(url, renv)

    payload = renv.get("payload", {})
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected dict payload: '{payload}'")

    return payload


class FossilPoller(base.ReconfigurablePollingChangeSource, StateMixin):
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
        repourl: str,
        rss: bool = False,
        name: Optional[str] = None,
        pollInterval: int = 10 * 60,
        pollAtLaunch: bool = False,
        pollRandomDelayMin: int = 0,
        pollRandomDelayMax: int = 0,
    ):
        """
        Fossil SCM poller.

        Regularly check the Fossil repository at `repourl` for new commits and
        submit them to the Buildbot master.

        Parameters
        ----------
        repourl
            Base URL of the Fossil repository without a trailing `/`. Only HTTP and
            HTTPS URLs are supported.

        rss
            Use `{repourl}/timeline.rss` instead of Fossil's JSON API to get new commits.
            JSON is preferred (and default) because RSS does not provide a list of changed
            files in a commit, but JSON support is not always configured in the Fossil
            server.

        name
            The name of the poller defaults to `repourl`, but can be changed with this
            parameter. This name is also used by Buildbot's `/change_hook/poller` hook.

        pollInterval
            Interval between polls, in seconds.

        pollAtLaunch
            Poll immediately at launch instead of waiting a poll interval before the first
            poll.

        pollRandomDelayMin, pollRandomDelayMax
            Set to randomize the polling interval to even out the load if there are many
            pollers to the same repository.
        """
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
        if rss not in (True, False):
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
        cookie = yield self.getState("login_cookie", None)
        if cookie:
            http_headers["Cookie"] = cookie

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
        try:
            if not self.rss:
                changes = yield self._fetch_json()
            else:
                changes = yield self._fetch_rss()

            yield self._process_changes(changes)

        except (HTTPError, JSONError) as exc:
            log.error(str(exc))

    @defer.inlineCallbacks
    def _fetch_json(self):
        # The /json/timeline/checkin API takes the following parameters:
        # - files=bool enables the `files` list.
        # - tag|branch=string only sends checkins for a specific branch.
        # See https://fossil-scm.org/home/doc/trunk/www/json-api/api-timeline.md
        try:
            payload = yield self._json_get("timeline/checkin", files=True)
        except JSONAuthError as exc:
            log.info(str(exc))
            yield self._json_login()
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
    def _json_login(self):
        """Try logging in with the JSON API"""
        # Always use the anonymous login procedure. This will usually give us the 'h'
        # permission necessary for the timeline/checkin endpoint. It's possible to
        # configure Fossil differently, so we may need to add user/password login in the
        # future.
        #
        # See https://fossil-scm.org/home/doc/trunk/www/json-api/api-auth.md#login-anonymous
        log.info("Getting anonymous passsword for {repourl}", repourl=self.repourl)
        anonpw = yield self._json_get("anonymousPassword")
        log.info("Got anonymous password and seed={seed}", **anonpw)
        response = yield self._http.post(
            "/json/login",
            json={
                "payload": {
                    "name": "anonymous",
                    "password": anonpw["password"],
                    "anonymousSeed": anonpw["seed"],
                }
            },
        )
        login = yield json_payload(self.repourl + "/json/login", response)
        log.info("Logged in as {name} with cookie {loginCookieName}", **login)

        # The login response actually comes with a Set-Cookie header, but
        # HTTPClientService doesn't track cookies. We'll set the Cookie header manually.
        cookie = login["loginCookieName"] + "=" + login["authToken"]
        self._http.updateHeaders(dict(Cookie=cookie))
        yield self.setState("login_cookie", cookie)

    @defer.inlineCallbacks
    def _json_get(self, endpoint, **kwargs):
        """
        Make a JSON GET request to /json/{endpoint}.

        Returns the returned payload as a dict.
        """
        path = "/json/" + endpoint
        response = yield self._http.get(path, params=kwargs)
        payload = yield json_payload(self.repourl + path, response)
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
