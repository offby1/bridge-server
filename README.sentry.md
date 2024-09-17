# Wassup

Sentry seems slick, but they use a ton of terminology without clearly explaining it.

https://docs.sentry.io/concepts/key-terms/key-terms/ seems like it should define some of these ...

- event
  > An event is one instance of you sending us data. Generally, this is an error, but it’s possible to send us non-error related data as well.
- issue
  > An issue is a group of similar events. More details about why certain events are grouped together can be found here: https://docs.sentry.io/product/sentry-basics/guides/grouping-and-fingerprints/ but most often events are grouped because they’re triggered by the same part of your code, or, if that data isn’t available, because they are exceptions of the same type and value.
- span
  > span - A span is the basic unit that traces are composed of. Multiple groups of parent-child spans make up a trace in Sentry and share a trace_id,
- trace
  > trace - A trace is the record of the entire operation you want to measure or track - like page load, an instance of a user completing some action in your application, or a cron job in your backend.
- transaction
  > A transaction represents a single instance of a service being called to support an operation you want to measure or track, like a page load, page navigation, or asynchronous task.

It's quite expensive, too, although there's supposedly a way to [self-host](https://develop.sentry.dev/self-hosted/).
