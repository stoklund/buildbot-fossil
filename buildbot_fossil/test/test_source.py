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
FOSSIL_212_1 = """This is fossil version 2.12.1 [d4041437b6] 2021-01-28 20:42:53 UTC"""
FOSSIL_208 = """This is fossil version 2.8
JSON (API 20120713)
"""
JSON_STATUS = """{
	"fossil":"d4041437b6f40d0cc62f22d2973498d596af325b1d18fed2dd7584aef733df7a",
	"timestamp":1612721685,
	"command":"status",
	"procTimeUs":2678,
	"procTimeMs":2,
	"payload":{
		"repository":"/Users/jolesen/Fossils/buildbot-fossil.fossil",
		"localRoot":"/Users/jolesen/devel/buildbot-fossil/",
		"checkout":{
			"uuid":"9be9ceea32360ecb0fe0051681f8258e84665fd728c2ed69726550206619d2a7",
			"tags":["trunk", "release"],
			"datetime":"2021-02-07 17:46:17 UTC",
			"timestamp":1612719977
		},
		"files":[{
				"name":"buildbot_fossil/steps.py",
				"status":"edited"
			}],
		"errorCount":0
	}
}
"""


def expect_v215():
    """Expect a fossil version command, return v2.15"""
    return (
        ExpectShell(".", ["fossil", "version", "-verbose"], logEnviron=True)
        + ExpectShell.log("stdio", stdout=FOSSIL_215)
        + 0
    )


def expect_fossil_dot(*args):
    """Expect a fossil command in the . worker directory."""
    return ExpectShell(".", ["fossil"] + list(args), logEnviron=False)


def expect_fossil(*args):
    """Expect a fossil command in the normal wkdir directory."""
    return ExpectShell("wkdir", ["fossil"] + list(args), logEnviron=False)


def expect_open():
    """Expect a fossil open command"""
    return expect_fossil_dot("open", "wkdir.fossil", "--workdir", "wkdir", "--empty")


def expect_json_status():
    """Expect a json status command, return JSON example."""
    return expect_fossil("json", "status") + ExpectShell.log(
        "stdio", stdout=JSON_STATUS
    )


def interrupt_cmd(cmd):
    """Behavior callback which interrupts the current command."""
    cmd.set_run_interrupt()
    cmd.interrupt("test")


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
    def test_triple_version(self):
        """Some fossil versions are a.b.c."""
        self.setupStep(self.stepClass(REPOURL, mode="incremental"))
        self.expectCommands(
            ExpectShell(".", ["fossil", "version", "-verbose"])
            + ExpectShell.log("stdio", stdout=FOSSIL_212_1)
            + 0,
            expect_fossil_dot("pull", REPOURL, "-R", "wkdir.fossil") + 0,
            expect_fossil("revert") + 0,
            expect_fossil("checkout", "tip") + 0,
            expect_fossil("status", "--differ") + 0,
        )
        self.expectOutcome(result=SUCCESS)
        yield self.runStep()
        self.assertLogged("worker test has Fossil/21201, JSON/0")

    @defer.inlineCallbacks
    def test_mode_incremental(self):
        """Test the incremental mode, assuming clone and workdir already exist."""
        self.setupStep(self.stepClass(REPOURL, mode="incremental"))
        self.expectCommands(
            expect_v215(),
            expect_fossil_dot("pull", REPOURL, "-R", "wkdir.fossil") + 0,
            expect_fossil("revert") + 0,
            expect_fossil("checkout", "tip") + 0,
            expect_json_status() + 0,
        )
        self.expectOutcome(result=SUCCESS)
        self.expectProperty(
            "got_revision",
            "9be9ceea32360ecb0fe0051681f8258e84665fd728c2ed69726550206619d2a7",
            "Fossil",
        )
        self.expectProperty("got_tags", ["trunk", "release"], "Fossil")
        yield self.runStep()
        self.assertLogged("worker test has Fossil/21500, JSON/20120713")

    @defer.inlineCallbacks
    def test_mode_incremental_no_repo(self):
        """Test the incremental mode, assuming no repo exists."""
        self.setupStep(self.stepClass(REPOURL, mode="incremental"))
        self.expectCommands(
            expect_v215(),
            expect_fossil_dot("pull", REPOURL, "-R", "wkdir.fossil") + 1,
            # After pull fails, stat the repo clone to see if it exists.
            Expect("stat", {"file": "wkdir.fossil", "logEnviron": False}) + FAILURE,
            expect_fossil_dot("clone", REPOURL, "wkdir.fossil") + 0,
            # Then proceed as clobber/copy.
            Expect("rmdir", {"dir": "wkdir", "logEnviron": False}) + SUCCESS,
            expect_open() + 0,
            expect_fossil("checkout", "tip") + 0,
            expect_json_status() + 0,
        )
        self.expectOutcome(result=SUCCESS)
        yield self.runStep()

    @defer.inlineCallbacks
    def test_mode_incremental_bad_repo(self):
        """Pull fails, but there is a repo file. Don't try to fix it, fail instead."""
        self.setupStep(self.stepClass(REPOURL, mode="incremental"))
        self.expectCommands(
            expect_v215(),
            expect_fossil_dot("pull", REPOURL, "-R", "wkdir.fossil") + 1,
            # After pull fails, stat the repo clone to see if it exists.
            Expect("stat", {"file": "wkdir.fossil", "logEnviron": False}) + SUCCESS,
        )
        self.expectOutcome(result=FAILURE)
        yield self.runStep()

    @defer.inlineCallbacks
    def test_mode_incremental_cancelled_pull(self):
        """Cancelled during pull."""
        self.setupStep(self.stepClass(REPOURL, mode="incremental"))
        self.expectCommands(
            expect_v215(),
            expect_fossil_dot("pull", REPOURL, "-R", "wkdir.fossil")
            + Expect.behavior(interrupt_cmd),
        )
        self.expectOutcome(result=CANCELLED)
        yield self.runStep()

    @defer.inlineCallbacks
    def test_mode_incremental_revert_failed(self):
        """Revert fails, fall back to full/copy."""
        self.setupStep(self.stepClass(REPOURL, mode="incremental"))
        self.expectCommands(
            expect_v215(),
            expect_fossil_dot("pull", REPOURL, "-R", "wkdir.fossil") + 0,
            expect_fossil("revert") + 1,
            Expect("rmdir", {"dir": "wkdir", "logEnviron": False}) + SUCCESS,
            expect_open() + 0,
            expect_fossil("checkout", "tip") + 0,
            expect_json_status() + 0,
        )
        self.expectOutcome(result=SUCCESS)
        yield self.runStep()

    @defer.inlineCallbacks
    def test_mode_incremental_checkout_failed(self):
        """Test the incremental mode, assuming clone and workdir already exist."""
        self.setupStep(self.stepClass(REPOURL, mode="incremental"))
        self.expectCommands(
            expect_v215(),
            expect_fossil_dot("pull", REPOURL, "-R", "wkdir.fossil") + 0,
            expect_fossil("revert") + 0,
            expect_fossil("checkout", "tip") + 1,
        )
        self.expectOutcome(result=FAILURE)
        yield self.runStep()

    @defer.inlineCallbacks
    def test_mode_full_copy(self):
        """Test the full/copy mode, assuming clone already exists."""
        self.setupStep(self.stepClass(REPOURL, mode="full", method="copy"))
        self.changeWorkerSystem("win32")
        self.expectCommands(
            ExpectShell(".", ["fossil", "version", "-verbose"], logEnviron=True)
            + ExpectShell.log("stdio", stdout=FOSSIL_208)
            + 0,
            expect_fossil_dot("pull", REPOURL, "-R", "wkdir.fossil") + 0,
            Expect("rmdir", {"dir": "wkdir", "logEnviron": False}) + SUCCESS,
            Expect("mkdir", {"dir": "wkdir", "logEnviron": False}) + SUCCESS,
            expect_fossil("open", r"..\wkdir.fossil", "--empty") + 0,
            expect_fossil("checkout", "tip") + 0,
            expect_json_status() + 0,
        )
        self.expectOutcome(result=SUCCESS)
        self.expectProperty(
            "got_revision",
            "9be9ceea32360ecb0fe0051681f8258e84665fd728c2ed69726550206619d2a7",
            "Fossil",
        )
        self.expectProperty("got_tags", ["trunk", "release"], "Fossil")
        yield self.runStep()
        self.assertLogged("worker test has Fossil/20800, JSON/20120713")
