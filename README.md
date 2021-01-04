# Fossil plugin for Buildbot

[Fossil](https://fossil-scm.org/) is a software configuration management system.
This [Buildbot](https://buildbot.net) plugin provides two classes to use in
`master.cfg`:

1. `changes.FossilPoller` polls a Fossil HTTP server for new checkins.

2. `steps.Fossil` checks out a source revision from a Fossil repo before a build.

