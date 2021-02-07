"""Fossil source build step"""

import json
import re
from typing import Optional

from buildbot import config
from buildbot.interfaces import WorkerSetupError
from buildbot.process import buildstep, remotecommand
from buildbot.process.results import CANCELLED, FAILURE, SUCCESS
from buildbot.steps.source.base import Source
from buildbot.util.logger import Logger
from twisted.internet import defer

# First Fossil version that supports `open --workdir`
HAS_OPEN_WORKDIR = 21200


class Fossil(Source):
    log = Logger()
    name = "fossil"

    possible_methods = ("fresh", "copy", "clobber")

    def __init__(
        self,
        repourl: str = None,
        mode: str = "incremental",
        method: Optional[str] = None,
        **kwargs,
    ):
        """
        Check out a revision from the Fossil SCM.

        Parameters
        ----------
        repourl
            URL of the upstream Fossil repository. This can be any URL supported by
            :command:`fossil clone`.

        mode
            One of "full" or "incremental". In the default "incremental" mode, build files
            are left in place in the `workdir`, and only :command:`fossil revert` is used to
            clean up before :command:`fossil update` checks out the new revision. This
            enables fast, incremental builds. In "full" mode, the `workdir` is cleaned up
            more thoroughly as specified by the `method` parameter.

        method
            How to clean up the workdir in "full" mode. One of "fresh", "copy", or
            "clobber":

            - The "fresh" method runs :command:`fossil clean --verily` to delete all
              unversioned files in `workdir`.
            - The "copy" method deletes the entire `workdir` directory tree and makes a new
              checkout from the cloned `{workdir}.fossil` repository.
            - The "clobber" method deletes both the cloned repository and the `workdir` and
              starts over with a new clone from `repourl`.
        """

        self.repourl = repourl
        self.mode = mode
        self.method = method
        super().__init__(mode=mode, **kwargs)

        if mode == "incremental":
            if method is not None:
                config.error("method has no effect in incremental mode")
        elif mode == "full":
            if method not in self.possible_methods:
                config.error("method must be one of " + str(self.possible_methods))
        else:
            config.error("mode must be 'full' or 'incremental'")

        # Defined in run_vc():
        self.stdio_log = None
        self.repopath = None
        # Defined in check_fossil_version():
        self.fossil_version = None
        self.fossil_json = None

    @defer.inlineCallbacks
    def run_vc(self, branch, revision, patch):
        """Main entry point for source steps"""
        self.stdio_log = yield self.addLogForRemoteCommands("stdio")
        res = yield self.check_fossil_version()
        if res != SUCCESS:
            return res

        # Store the repo file as `build.fossil` next to the `build/` workdir.
        self.repopath = self.workdir.rstrip(r"\/") + ".fossil"

        # Bring the workdir to a state where only an update is needed.
        if self.mode == "incremental":
            yield self.msg("incremental update")
            res = yield self.incremental_clean()
        else:
            yield self.msg("full/{} checkout", self.method)
            res = yield self.full_clean(self.method)
        if res != SUCCESS:
            return res

        res = yield self.fossil_checkout(branch, revision)
        if res != SUCCESS:
            return res

        if patch:
            yield self.patch(patch)

        # Run fossil status after applying the patch to show changes in the
        # stdio log.
        res = yield self.fossil_status()
        return res

    def msg(self, fmt, *args, **kwargs):
        """
        Add a message to the stdio header log and make sure it stands out.

        Arguments after `fmt` are like `fmt.format()`
        """
        text = fmt.format(*args, **kwargs)
        return self.stdio_log.addHeader("\n=== " + text + " ===\n")

    @defer.inlineCallbacks
    def check_fossil_version(self):
        """Check that the worker has a fossil executable and get its version."""
        yield self.msg("checking fossil version")
        cmd = yield self.fossil("version", "-verbose", workdir=".", collectStdout=True)
        if cmd.didFail():
            raise WorkerSetupError("fossil is not installed on worker")
        if cmd.results() != SUCCESS:
            return cmd.results()

        match = re.match(r"This is fossil version (\d+(\.\d+)+)", cmd.stdout)
        if not match:
            raise WorkerSetupError("unrecognized fossil version")
        # Use the same encoding as Fossil's own RELEASE_VERSION_NUMBER.
        self.fossil_version = sum(
            int(v) * s for v, s in zip(match[1].split("."), (10000, 100, 1))
        )

        match = re.search(r"^JSON \(API (\d+)\)$", cmd.stdout, re.MULTILINE)
        self.fossil_json = int(match[1]) if match else 0

        self.log.info(
            "worker {name} has Fossil/{version}, JSON/{json}",
            name=self.worker.workername,
            version=self.fossil_version,
            json=self.fossil_json,
        )
        return SUCCESS

    @defer.inlineCallbacks
    def incremental_clean(self):
        """
        Attempt an incremental mode update, or fall back to a full checkout.

        A normal incremental update assumes that `workdir` already contains a
        checkout:

            fossil revert
            fossil update $revision

        The revert ensures that any changed to versioned files are reverted,
        but any extra files in the workdir are preserved.
        """
        repo_status = yield self.update_repo()
        if repo_status != SUCCESS:
            yield self.msg("no repo found, cloning")
            res = yield self.full_clean("copy", repo_status)
            return res

        cmd = yield self.fossil("revert")
        if not cmd.didFail():
            return cmd.results()

        yield self.msg("failed to revert, using full/copy checkout")
        res = yield self.full_clean("copy", repo_status)
        return res

    @defer.inlineCallbacks
    def full_clean(self, method, repo_status=None):
        """
        Perform a full mode checkout according to `method`.

        If the repository has already been updated, pass the status in `repo_status`.
        """
        # Fall back to clobber unless we have a good repo clone.
        if method == "clobber":
            yield self.runRmFile(self.repopath, abandonOnFailure=False)
        else:
            if repo_status is None:
                repo_status = yield self.update_repo()
            if repo_status != SUCCESS:
                method = "clobber"

        if method == "clobber":
            cmd = yield self.fossil("clone", self.repourl, self.repopath, workdir=".")
            if cmd.results() != SUCCESS:
                return cmd.results()
            # After cloning, proceed as 'copy'
            method = "copy"

        # We now have a good repo.

        # Clean can fail if the workdir isn't a proper checkout,
        # or if it is in a very bad state. Fall back to 'copy'
        if method == "fresh":
            cmd = yield self.fossil("clean", "--verily")
            if cmd.results() == SUCCESS:
                cmd = yield self.fossil("revert")

            if cmd.didFail():
                yield self.msg("problem cleaning, falling back to full/copy")
                method = "copy"
            else:
                # succeeded or cancelled, don't delete anything.
                return cmd.results()

        if method == "copy":
            yield self.runRmdir(self.workdir)
            res = yield self.fossil_open()
            if res != SUCCESS:
                return res

        return SUCCESS

    @defer.inlineCallbacks
    def update_repo(self):
        """
        Check that the repo file exists and pull in changes from the remote.

        Returns `SUCCESS` for a good repo, `FAILURE` if the repo is missing or broken.
        """
        # Some that `pull` doesn't return an error code on network problems.
        cmd = yield self.fossil("pull", self.repourl, "-R", self.repopath, workdir=".")
        if cmd.results() != FAILURE:
            return cmd.results()

        # The pull failed. If this is because the repo file is missing, we want to try a
        # clone. Otherwise, fail the whole buildstep. Don't attempt to repair a repo
        # when we don't understand the problem.
        repo_exists = yield self.pathExists(self.repopath)
        if repo_exists:
            self.log.error(
                "Problem with existing Fossil repo {repo}", repo=self.repopath
            )
            raise buildstep.BuildStepFailed()

        return FAILURE

    @defer.inlineCallbacks
    def fossil_open(self):
        """
        Open the `self.repopath` repo in `self.workdir`.

        Assume that the workdir does not exist.
        """
        if self.fossil_version >= HAS_OPEN_WORKDIR:
            cmd = yield self.fossil(
                "open", self.repopath, "--workdir", self.workdir, "--empty", workdir="."
            )
            return cmd.results()

        # We have an older fossil which doesn't support the --workdir option.
        yield self.runMkdir(self.workdir)

        # We need to refer to the repo file using the worker's path syntax.
        pathm = self.build.path_module
        repo = pathm.join("..", pathm.split(self.repopath)[1])
        cmd = yield self.fossil("open", repo, "--empty")
        return cmd.results()

    @defer.inlineCallbacks
    def fossil_checkout(self, branch, revision):
        """
        Update workdir to the right revision.

        The `steps.Source` parent handles the `alwaysUseLatest` and `branch`
        configuration options and translate them to the `revision` and `branch`
        parameters we receive here.

        If neither a revision or branch are supplied, we will check out `tip`
        which is the latest commit on any branch in the repo.
        """
        if revision:
            version = revision
        elif branch:
            version = "tag:" + branch
        else:
            version = "tip"

        cmd = yield self.fossil("checkout", version)
        return cmd.results()

    @defer.inlineCallbacks
    def fossil_status(self):
        """Check the status of the checkout, set build properties."""
        # Prefer the json status command if it is available. It gives us all the digits
        # of SHA-256 hashes, and it is likely more stable.
        if self.fossil_json > 0:
            cmd = yield self.fossil("json", "status", collectStdout=True)
            if cmd.results() != SUCCESS:
                return cmd.results()

            checkout = json.loads(cmd.stdout)["payload"]["checkout"]
            self.updateSourceProperty("got_revision", checkout["uuid"])
            self.updateSourceProperty("got_tags", checkout["tags"])
        else:
            # No JSON API available
            cmd = yield self.fossil("status", "--differ", collectStdout=True)
            if cmd.results() != SUCCESS:
                return cmd.results()

            # Extract got_revision from the status output.
            match = re.search(r"^checkout:\s+([0-9a-f]+)", cmd.stdout, re.MULTILINE)
            if match:
                self.updateSourceProperty("got_revision", match[1])

            match = re.search(r"^tags:\s+(.+)$", cmd.stdout, re.MULTILINE)
            if match:
                self.updateSourceProperty("got_tags", match[1].split(", "))

        return SUCCESS

    @defer.inlineCallbacks
    def fossil(self, *args, **kwargs):
        """
        Run a fossil command on the worker.

        Return the `RemoteShellCommand` so its `results()`, `rc`, and `stdout`
        attributes can be examined.

        @param args    Positional arguments for the `fossil` command.
        @param workdir Alternative working directory relative to the builder's
                       base.
        """
        workdir = kwargs.pop("workdir", self.workdir)
        command = ["fossil"] + list(args)

        for arg in ("env", "logEnviron", "timeout"):
            if arg not in kwargs:
                kwargs[arg] = getattr(self, arg)

        cmd = remotecommand.RemoteShellCommand(workdir, command, **kwargs)
        cmd.useLog(self.stdio_log, False)
        yield self.runCommand(cmd)
        if cmd.results() == CANCELLED:
            raise buildstep.BuildStepCancelled()

        # There is no reason to keep repeating the environment in the logs.
        self.logEnviron = False

        return cmd
