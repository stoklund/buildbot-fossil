"""Unit tests for the Fossil source step."""

from buildbot.process.results import SUCCESS
from buildbot.test.fake.remotecommand import ExpectShell
from buildbot.test.util import config, sourcesteps
from buildbot.test.util.misc import TestReactorMixin
from twisted.trial import unittest

from ..steps import Fossil

REPOURL = "https://fossil-scm.example/home"


class TestFossil(
    sourcesteps.SourceStepMixin,
    config.ConfigErrorsMixin,
    TestReactorMixin,
    unittest.TestCase,
):

    stepClass = Fossil

    def setUp(self):
        self.setUpTestReactor()
        self.sourceName = self.stepClass.__name__
        return self.setUpSourceStep()

    def tearDown(self):
        return self.tearDownSourceStep()

    def test_mode_incremental(self):
        """Test the incremental mode, assuming clone and workdir already exist."""
        self.setupStep(self.stepClass(REPOURL, mode="incremental"))
        self.expectCommands(
            ExpectShell(workdir=".", command=["fossil", "remote", "-R", "wkdir.fossil"])
            + ExpectShell.log("stdio", stdout=REPOURL)
            + 0,
            ExpectShell(workdir="wkdir", command=["fossil", "revert"]) + 0,
            ExpectShell(workdir="wkdir", command=["fossil", "update", "tip"]) + 0,
            ExpectShell(workdir="wkdir", command=["fossil", "status", "--differ"]) + 0,
        )
        self.expectOutcome(result=SUCCESS)
        return self.runStep()
