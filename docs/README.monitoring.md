# What to monitor and how

I don't yet know what I need from monitoring.

I have a branch that adds prometheus and grafana; iirc they work fine there.  I haven't bothered merging it into main.

I also have a branch where I'm poking at fluentd for log collection.

I just came across [opentelemetry](https://opentelemetry.io/ecosystem/demo/), and it is awfully slick.  Seems to solve the same problems as prometheus *and* fluentd, all bundled together.

[grafana/otel-lgtm](https://hub.docker.com/r/grafana/otel-lgtm) looks like an easy way to get started with it.  Blurb [here](https://grafana.com/blog/2024/03/13/an-opentelemetry-backend-in-a-docker-image-introducing-grafana/otel-lgtm/).
