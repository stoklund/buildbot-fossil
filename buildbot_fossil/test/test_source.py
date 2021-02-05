"""Unit tests for the Fossil source step."""

from buildbot.process.results import SUCCESS
from buildbot.test.fake.remotecommand import ExpectShell
from buildbot.test.util import config, sourcesteps
from buildbot.test.util.logging import LoggingMixin
from buildbot.test.util.misc import TestReactorMixin
from twisted.internet import defer
from twisted.trial import unittest

from ..steps import Fossil

REPOURL = "https://fossil-scm.example/home"
FOSSIL_215 = """This is fossil version 2.15 [d4041437b6] 2021-01-28 20:42:53 UTC
Compiled on Jan 29 2021 16:37:52 using clang-12.0.0 (clang-1200.0.32.29) (64-bit)
Schema version 2015-01-24
Detected memory page size is 4096 bytes
zlib 1.2.11, loaded 1.2.11
hardened-SHA1 by Marc Stevens and Dan Shumow
SSL (OpenSSL 1.1.1i  8 Dec 2020)
FOSSIL_ENABLE_LEGACY_MV_RM
JSON (API 20120713)
MARKDOWN
UNICODE_COMMAND_LINE
FOSSIL_DYNAMIC_BUILD
SQLite 3.35.0 2021-01-27 19:15:06 9dc7fc9f04
"""


class TestFossil(
    sourcesteps.SourceStepMixin,
    config.ConfigErrorsMixin,
    TestReactorMixin,
    LoggingMixin,
    unittest.TestCase,
):

    stepClass = Fossil

    def setUp(self):
        self.source_name = self.stepClass.__name__
        self.setUpTestReactor()
        self.setUpLogging()
        return self.setUpSourceStep()

    def tearDown(self):
        return self.tearDownSourceStep()

    @defer.inlineCallbacks
    def test_mode_incremental(self):
        """Test the incremental mode, assuming clone and workdir already exist."""
        self.setupStep(self.stepClass(REPOURL, mode="incremental"))
        self.expectCommands(
            ExpectShell(workdir=".", command=["fossil", "version", "-verbose"])
            + ExpectShell.log("stdio", stdout=FOSSIL_215)
            + 0,
            ExpectShell(workdir=".", command=["fossil", "remote", "-R", "wkdir.fossil"])
            + ExpectShell.log("stdio", stdout=REPOURL)
            + 0,
            ExpectShell(workdir="wkdir", command=["fossil", "revert"]) + 0,
            ExpectShell(workdir="wkdir", command=["fossil", "update", "tip"]) + 0,
            ExpectShell(workdir="wkdir", command=["fossil", "status", "--differ"]) + 0,
        )
        self.expectOutcome(result=SUCCESS)
        yield self.runStep()
        self.assertLogged("worker test has Fossil/21500, JSON/20120713")
