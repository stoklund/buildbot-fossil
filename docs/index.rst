Fossil plugin for Buildbot
==========================

Fossil_ is a software configuration management system. This Buildbot_ plugin
provides two classes for use in your Buildbot `master.cfg`:

1. :class:`changes.FossilPoller` polls a Fossil HTTP server for new checkins.
2. :class:`steps.Fossil` checks out a source revision from a Fossil repository before a build.

This plugin makes it possible to use Buildbot as a continuous integration server
for projects being developed in a Fossil repository.

Installation
------------

Install the buildbot-fossil package from PyPI_ on the machine running Buildbot:

.. code-block:: shell

    pip install buildbot-fossil

The package is automatically registered as a Buildbot plugin, so the two new
classes appear as :class:`buildbot.plugins.changes.FossilPoller` and
:class:`buildbot.plugins.steps.Fossil`, ready to be used in the `master.cfg`
configuration file.

Polling for commits
-------------------

Buildbot learns about new commits from its `change sources`_. Add a Fossil
change source to `master.cfg` to poll for changes in a Fossil repository served
over HTTP::

    from buildbot.plugins import changes
    ...
    c['change_source'] = changes.FossilPoller('https://fossil-scm.example/home')

By default, the Fossil repository is polled every 10 minutes using the JSON API.

.. autoclass:: changes.FossilPoller

Configuring an after-receive hook
---------------------------------

Polling alone works fine, but it causes delays between committing a change and
Buildbot noticing the change and testing it. The delays can be avoided by
installing a `Fossil after-receive hook`_ which tells Buildbot to poll
immediately.

The hook needs the URL where the Fossil repository is served (actually, the
poller name), and the Buildbot URL. The :command:`curl` command must be available:

.. code-block:: shell

    #!/bin/sh
    #
    # Install: after-receive.sh --install /path/to/repo.fossil

    if [ "$1" == "--install" ]; then
        sdir=$(cd "$(dirname "$0")" && pwd)
        fossil hook add -R "$2" --type after-receive --command "$sdir/after-receive.sh %R"
        exit
    fi

    repo="$(basename "$1" .fossil)"
    name="http://my.fossil.example/$repo"
    buildbot="https://server.example/buildbot"

    curl -s "$buildbot/change_hook/poller?poller=$name"

Fossil does provide some information to an after-receive hook on stdin, but this
script doesn't need it since it just causes Buildbot to turn around and poll the
Fossil server for any new changes.

Checking out sources on a worker
--------------------------------

Before testing a Fossil commit on a Buildbot worker, the sources must be checked
out on the worker. This is handled by the :class:`steps.Fossil` build step which
requires a :command:`fossil` executable installed on the worker machines. The
Fossil repository at `{repourl}` is cloned to a `{workdir}.fossil` file on the
worker and checked out in the `{workdir}` directory.

See also the Buildbot documentation of `source checkout operations`_.

.. autoclass:: steps.Fossil

.. _Fossil: https://fossil-scm.org/
.. _`Fossil after-receive hook`: https://fossil-scm.org/home/doc/trunk/www/hooks.md
.. _Buildbot: https://buildbot.net/
.. _PyPI: https://pypi.org/project/buildbot-fossil/
.. _`change sources`: https://docs.buildbot.net/current/manual/configuration/changesources.html
.. _`source checkout operations`: https://docs.buildbot.net/current/manual/configuration/steps/source_common.html