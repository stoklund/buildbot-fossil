"""Unit tests for the Fossil source step."""

from buildbot.interfaces import WorkerSetupError
from buildbot.process.results import CANCELLED, EXCEPTION, FAILURE, SUCCESS
from buildbot.test.fake.remotecommand import Expect, ExpectShell
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
    def test_fossil_not_installed(self):
        """Test the case where the fossil executable is not in PATH on the worker."""
        self.setupStep(self.stepClass(REPOURL))
        self.expectCommands(
            ExpectShell(".", ["fossil", "version", "-verbose"]) + FAILURE
        )
        self.expectException(WorkerSetupError)
        self.expectOutcome(result=EXCEPTION)
        yield self.runStep()
        self.assertLogged("WorkerSetupError: fossil is not installed on worker")

    @defer.inlineCallbacks
    def test_fossil_is_a_teapot(self):
        """Test the case where the fossil executable has lost its mind."""
        self.setupStep(self.stepClass(REPOURL))
        self.expectCommands(
            ExpectShell(".", ["fossil", "version", "-verbose"])
            + ExpectShell.log("stdio", stdout="I am a teapot!")
            + 0
        )
        self.expectException(WorkerSetupError)
        self.expectOutcome(result=EXCEPTION)
        yield self.runStep()
        self.assertLogged("WorkerSetupError: unrecognized fossil version")

    @defer.inlineCallbacks
    def test_mode_incremental(self):
        """Test the incremental mode, assuming clone and workdir already exist."""
        self.setupStep(self.stepClass(REPOURL, mode="incremental"))
        self.expectCommands(
            ExpectShell(".", ["fossil", "version", "-verbose"])
            + ExpectShell.log("stdio", stdout=FOSSIL_215)
            + 0,
            ExpectShell(".", ["fossil", "pull", REPOURL, "-R", "wkdir.fossil"]) + 0,
            ExpectShell("wkdir", ["fossil", "revert"]) + 0,
            ExpectShell("wkdir", ["fossil", "checkout", "tip"]) + 0,
            ExpectShell("wkdir", ["fossil", "status", "--differ"]) + 0,
        )
        self.expectOutcome(result=SUCCESS)
        yield self.runStep()
        self.assertLogged("worker test has Fossil/21500, JSON/20120713")

    @defer.inlineCallbacks
    def test_mode_incremental_no_repo(self):
        """Test the incremental mode, assuming no repo exists."""
        self.setupStep(self.stepClass(REPOURL, mode="incremental"))
        self.expectCommands(
            ExpectShell(".", ["fossil", "version", "-verbose"])
            + ExpectShell.log("stdio", stdout=FOSSIL_215)
            + 0,
            ExpectShell(".", ["fossil", "pull", REPOURL, "-R", "wkdir.fossil"]) + 1,
            # After pull fails, stat the repo clone to see if it exists.
            Expect("stat", {"file": "wkdir.fossil", "logEnviron": True}) + FAILURE,
            ExpectShell(".", ["fossil", "clone", REPOURL, "wkdir.fossil"]) + 0,
            # Then proceed as clobber/copy.
            Expect("rmdir", {"dir": "wkdir", "logEnviron": True}) + SUCCESS,
            ExpectShell(
                ".",
                [
                    "fossil",
                    "open",
                    "wkdir.fossil",
                    "--workdir",
                    "wkdir",
                    "--empty",
                ],
            )
            + 0,
            ExpectShell("wkdir", ["fossil", "checkout", "tip"]) + 0,
            ExpectShell("wkdir", ["fossil", "status", "--differ"]) + 0,
        )
        self.expectOutcome(result=SUCCESS)
        yield self.runStep()

    @defer.inlineCallbacks
    def test_mode_incremental_bad_repo(self):
        """Pull fails, but there is a repo file. Don't try to fix it, fail instead."""
        self.setupStep(self.stepClass(REPOURL, mode="incremental"))
        self.expectCommands(
            ExpectShell(".", ["fossil", "version", "-verbose"])
            + ExpectShell.log("stdio", stdout=FOSSIL_215)
            + 0,
            ExpectShell(".", ["fossil", "pull", REPOURL, "-R", "wkdir.fossil"]) + 1,
            # After pull fails, stat the repo clone to see if it exists.
            Expect("stat", {"file": "wkdir.fossil", "logEnviron": True}) + SUCCESS,
        )
        self.expectOutcome(result=FAILURE)
        yield self.runStep()
