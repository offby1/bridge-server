# Perf notes

https://chatgpt.com/c/685066f3-4d4c-8013-b496-e0f00ab9e643 suggests (I had suspected this might be possible) django eventstream is holding open lots of connections, which might somehow be causing the rest of the app to fight over the remaining connections.

## pyinstrument

This is the nicest profiler I've found so far.  I can use it in two ways; both are enabled by setting `PYINSTRUMENT` to `t` in the environment.

* `just test` will run the unit tests as usual, but when they're done, it'll spew a cute text-mode call graph showing which functions took how long.

* `just runme` will work normally, but you can append `?profile` to any URL, and it'll render a slick flamegraph, instead of the usual page content.

BUT! If I have it enabled in docker, for a "stress" run, by setting `PYINSTRUMENT_PROFILE_DIR = "profiles"` in settings, it seems to consume gigabytes of RAM, and also (I suspect) slow things down on its own.   As of 2025-06-17T14:45:51-0700 there are [three open issues](https://github.com/joerick/pyinstrument/issues?q=is%3Aissue%20state%3Aopen%20memory) complaining about memory usage.

## py-spy

I once managed to get py-spy working on MacOS (it wasn't easy); I have not been able to reproduce this success.  It works fine in the docker container, though.  Use it there like this:

```shell
$ docker compose exec -it django bash
# htop # to find out the PID you care about (typically daphne)
# poetry run py-spy top --pid PID
```

## Other ideas to explore

### [Sentry](https://eric-hanchrow.sentry.io/releases/56beb2495cce905f8fa43bbfbf98d3713f790fdf/?project=4507936354205696)

...has already pointed out an ["N+1 query" problem](https://docs.djangoproject.com/en/5.1/topics/db/optimization/#retrieve-everything-at-once-if-you-know-you-will-need-it)

Starting from <https://docs.djangoproject.com/en/5.1/topics/performance/>

### <https://awesomedjango.org/#performance>

| status | what                                                                                                                                                                                                                                                                                                                             |
|--------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| _      | <https://github.com/adamchainz/django-perf-rec>                                                                                                                                                                                                                                                                                  |
| _      | [new relic wozzit](https://docs.newrelic.com/docs/apm/agents/python-agent/supported-features/optional-manual-browser-instrumentation-django-templates/)                                                                                                                                                                          |
| _      | [scout apm](https://scoutapm.com/docs/python/django)                                                                                                                                                                                                                                                                             |
| ⌧      | [silk](https://github.com/jazzband/django-silk)<br>Not very compelling                                                                                                                                                                                                                                                           |
| 😃     | [pyinstrument](https://pyinstrument.readthedocs.io/en/latest/)<br>Pretty nice!                                                                                                                                                                                                                                                   |
| ✓      | [google](https://pagespeed.web.dev/analysis/https-teensy-info-tail571dc2-ts-net/7cmlfztwtz?form_factor=mobile) suggests that the problem is the debug toolbar!<br> Which indeed it was.<br>Oh, and Chrome's developer tools now have something called "Lighthouse" built-in, which at first glance appears to be the same thing. |
