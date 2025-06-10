# What to monitor and how

I don't yet know what I need from monitoring.

I have added sentry, prometheus, and grafana; they work fine. However, I don't really udnerstand what they're showing me, apart from obvious stuff like logs (in sentry) and e.g. request latency from prometheus/grafana.

I also have a branch where I'm poking at fluentd for log collection.

I just came across [opentelemetry](https://opentelemetry.io/ecosystem/demo/), and it is awfully slick.  Seems to solve the same problems as prometheus *and* fluentd, all bundled together.

[grafana/otel-lgtm](https://hub.docker.com/r/grafana/otel-lgtm) looks like an easy way to get started with it.  Blurb [here](https://grafana.com/blog/2024/03/13/an-opentelemetry-backend-in-a-docker-image-introducing-grafana/otel-lgtm/).

## wtf are "spans", "traces", &c in sentry?

https://docs.sentry.io/concepts/key-terms/tracing/distributed-tracing/#traces-transactions-and-spans

- trace
  "A trace is the record of the entire operation you want to measure or track - like page load, an instance of a user completing some action in your application, or a cron job in your backend." Counterintuitively, then, "spans" are smaller than "traces".

- transaction
  "A transaction represents a single instance of a service being called to support an operation you want to measure or track, like a page load, page navigation, or asynchronous task."

- span
  "A span is the basic unit that traces are composed of."  Ok er so uh ...
  "Every span may be the parent span to multiple child spans. One span in every transaction represents the transaction itself, with all other spans descending from that root span."

- event
  "An error or a transaction."

My take:

- A trace is either a *sequence*, or just a collection, of transactions; each transaction applies to a single service.  So it's the top-level thing.
- A transaction is a *tree* of spans.  Spans are recursive.  The topmost span in a tree o' spans corresponds to a transaction.
