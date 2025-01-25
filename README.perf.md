# Perf notes

## pytest-profiling
Just run `just t --profile-svg`, and it'll run the tests and collect profile data; then you can open an SVG page (whose path will be displayed) to see a complex graph that shows who calls whom and how long it takes, &c.
## py-spy

I once managed to get py-spy working on MacOS (it wasn't easy); I have not been able to reproduce this success.  It works fine in the docker container, though.

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
