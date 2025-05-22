# What's all this, then?

Problem: as I'm hacking away, I often stumble onto pages that give a 500, typically because I forgot to check that the player is logged in, or something similarly dumb.

I keep hitting these things, so clearly it's not enough for me to be more vigilant as I hack; I need something more reliable.

So: this branch will add a few unit tests that invoke some of the trickier views (app:hand-detail and app:hand-archive to start) with various combinations of hand states and player states, and check *only* that there are no exceptions, and that the responses are reasonable (i.e., 2xx, 3xx, or 4xx if appropriate).

`test_archive_view.py`'s `test_archive_view` is an example of such a test.
