"""Unit tests for the Fossil source step."""

from buildbot.interfaces import WorkerSetupError
from buildbot.process.results import CANCELLED, EXCEPTION, FAILURE, SUCCESS
from buildbot.test.steps import Expect, ExpectShell
from buildbot.test.reactor import TestReactorMixin
from buildbot.test.util import config, sourcesteps
from buildbot.test.util.logging import LoggingMixin
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
        ExpectShell(".", ["fossil", "version", "-verbose"], log_environ=True)
        .stdout(FOSSIL_215)
        .exit(0)
    )


def expect_fossil_dot(*args):
    """Expect a fossil command in the . worker directory."""
    return ExpectShell(".", ["fossil"] + list(args), log_environ=False)


def expect_fossil(*args):
    """Expect a fossil command in the normal wkdir directory."""
    return ExpectShell("wkdir", ["fossil"] + list(args), log_environ=False)


def expect_open():
    """Expect a fossil open command"""
    return expect_fossil_dot("open", "wkdir.fossil", "--workdir", "wkdir", "--empty")


def expect_json_status():
    """Expect a json status command, return JSON example."""
    return expect_fossil("json", "status").stdout(JSON_STATUS)


def interrupt_cmd(cmd):
    """Behavior callback which interrupts the current command."""
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
        self.setup_test_reactor()
        self.setUpLogging()
        return self.setUpSourceStep()

    def tearDown(self):
        return self.tearDownSourceStep()

    @defer.inlineCallbacks
    def test_fossil_not_installed(self):
        """Test the case where the fossil executable is not in PATH on the worker."""
        self.setup_step(self.stepClass(REPOURL))
        self.expect_commands(
            ExpectShell(".", ["fossil", "version", "-verbose"]).exit(1)
        )
        self.expect_exception(WorkerSetupError)
        self.expect_outcome(result=EXCEPTION)
        yield self.run_step()
        self.assertLogged("WorkerSetupError: fossil is not installed on worker")

    @defer.inlineCallbacks
    def test_fossil_is_a_teapot(self):
        """Test the case where the fossil executable has lost its mind."""
        self.setup_step(self.stepClass(REPOURL))
        self.expect_commands(
            ExpectShell(".", ["fossil", "version", "-verbose"])
            .stdout("I am a teapot!")
            .exit(0)
        )
        self.expect_exception(WorkerSetupError)
        self.expect_outcome(result=EXCEPTION)
        yield self.run_step()
        self.assertLogged("WorkerSetupError: unrecognized fossil version")

    @defer.inlineCallbacks
    def test_triple_version(self):
        """Some fossil versions are a.b.c."""
        self.setup_step(self.stepClass(REPOURL, mode="incremental"))
        self.expect_commands(
            ExpectShell(".", ["fossil", "version", "-verbose"])
            .stdout(FOSSIL_212_1)
            .exit(0),
            expect_fossil_dot("pull", REPOURL, "-R", "wkdir.fossil").exit(0),
            expect_fossil("revert").exit(0),
            expect_fossil("checkout", "tip").exit(0),
            expect_fossil("status", "--differ").exit(0),
        )
        self.expect_outcome(result=SUCCESS)
        yield self.run_step()
        self.assertLogged("worker test has Fossil/21201, JSON/0")

    @defer.inlineCallbacks
    def test_mode_incremental(self):
        """Test the incremental mode, assuming clone and workdir already exist."""
        self.setup_step(self.stepClass(REPOURL, mode="incremental"))
        self.expect_commands(
            expect_v215(),
            expect_fossil_dot("pull", REPOURL, "-R", "wkdir.fossil").exit(0),
            expect_fossil("revert").exit(0),
            expect_fossil("checkout", "tip").exit(0),
            expect_json_status().exit(0),
        )
        self.expect_outcome(result=SUCCESS)
        self.expect_property(
            "got_revision",
            "9be9ceea32360ecb0fe0051681f8258e84665fd728c2ed69726550206619d2a7",
            "Fossil",
        )
        self.expect_property("got_tags", ["trunk", "release"], "Fossil")
        yield self.run_step()
        self.assertLogged("worker test has Fossil/21500, JSON/20120713")

    @defer.inlineCallbacks
    def test_mode_incremental_no_repo(self):
        """Test the incremental mode, assuming no repo exists."""
        self.setup_step(self.stepClass(REPOURL, mode="incremental"))
        self.expect_commands(
            expect_v215(),
            expect_fossil_dot("pull", REPOURL, "-R", "wkdir.fossil").exit(1),
            # After pull fails, stat the repo clone to see if it exists.
            Expect("stat", {"file": "wkdir.fossil", "logEnviron": False}).exit(1),
            expect_fossil_dot("clone", REPOURL, "wkdir.fossil").exit(0),
            # Then proceed as clobber/copy.
            Expect("rmdir", {"dir": "wkdir", "logEnviron": False}).exit(0),
            expect_open().exit(0),
            expect_fossil("checkout", "tip").exit(0),
            expect_json_status().exit(0),
        )
        self.expect_outcome(result=SUCCESS)
        yield self.run_step()

    @defer.inlineCallbacks
    def test_mode_incremental_bad_repo(self):
        """Pull fails, but there is a repo file. Don't try to fix it, fail instead."""
        self.setup_step(self.stepClass(REPOURL, mode="incremental"))
        self.expect_commands(
            expect_v215(),
            expect_fossil_dot("pull", REPOURL, "-R", "wkdir.fossil").exit(1),
            # After pull fails, stat the repo clone to see if it exists.
            Expect("stat", {"file": "wkdir.fossil", "logEnviron": False}).exit(0),
        )
        self.expect_outcome(result=FAILURE)
        yield self.run_step()

    @defer.inlineCallbacks
    def test_mode_incremental_cancelled_pull(self):
        """Cancelled during pull."""
        self.setup_step(self.stepClass(REPOURL, mode="incremental"))
        self.expect_commands(
            expect_v215(),
            expect_fossil_dot("pull", REPOURL, "-R", "wkdir.fossil").behavior(
                interrupt_cmd
            ),
        )
        self.expect_outcome(result=CANCELLED)
        yield self.run_step()

    @defer.inlineCallbacks
    def test_mode_incremental_revert_failed(self):
        """Revert fails, fall back to full/copy."""
        self.setup_step(self.stepClass(REPOURL, mode="incremental"))
        self.expect_commands(
            expect_v215(),
            expect_fossil_dot("pull", REPOURL, "-R", "wkdir.fossil").exit(0),
            expect_fossil("revert").exit(1),
            Expect("rmdir", {"dir": "wkdir", "logEnviron": False}).exit(0),
            expect_open().exit(0),
            expect_fossil("checkout", "tip").exit(0),
            expect_json_status().exit(0),
        )
        self.expect_outcome(result=SUCCESS)
        yield self.run_step()

    @defer.inlineCallbacks
    def test_mode_incremental_checkout_failed(self):
        """Test the incremental mode, assuming clone and workdir already exist."""
        self.setup_step(self.stepClass(REPOURL, mode="incremental"))
        self.expect_commands(
            expect_v215(),
            expect_fossil_dot("pull", REPOURL, "-R", "wkdir.fossil").exit(0),
            expect_fossil("revert").exit(0),
            expect_fossil("checkout", "tip").exit(1),
        )
        self.expect_outcome(result=FAILURE)
        yield self.run_step()

    @defer.inlineCallbacks
    def test_mode_full_copy(self):
        """Test the full/copy mode, assuming clone already exists."""
        self.setup_step(self.stepClass(REPOURL, mode="full", method="copy"))
        self.change_worker_system("win32")
        self.expect_commands(
            ExpectShell(".", ["fossil", "version", "-verbose"], log_environ=True)
            .stdout(FOSSIL_208)
            .exit(0),
            expect_fossil_dot("pull", REPOURL, "-R", "wkdir.fossil").exit(0),
            Expect("rmdir", {"dir": "wkdir", "logEnviron": False}).exit(0),
            Expect("mkdir", {"dir": "wkdir", "logEnviron": False}).exit(0),
            expect_fossil("open", r"..\wkdir.fossil", "--empty").exit(0),
            expect_fossil("checkout", "tip").exit(0),
            expect_json_status().exit(0),
        )
        self.expect_outcome(result=SUCCESS)
        self.expect_property(
            "got_revision",
            "9be9ceea32360ecb0fe0051681f8258e84665fd728c2ed69726550206619d2a7",
            "Fossil",
        )
        self.expect_property("got_tags", ["trunk", "release"], "Fossil")
        yield self.run_step()
        self.assertLogged("worker test has Fossil/20800, JSON/20120713")
