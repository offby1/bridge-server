I was controlling hand 31; the others are bots.

Note how in both logs for me playing a hand, the previous log -- from "someone else" -- arrived *just before*.

```
2024-09-22T18:54:17.749Z : Play event listener saw ♠A from 32, so it fetched /table/214/four-hands and /table/214/handaction-summary-status 214:348:21
2024-09-22T18:54:17.937Z : Play event listener saw ♠9 from 31, so it fetched /table/214/four-hands and /table/214/handaction-summary-status 214:348:21
2024-09-22T18:54:19.016Z : Play event listener saw ♠6 from 10, so it fetched /table/214/four-hands and /table/214/handaction-summary-status 214:348:21
2024-09-22T18:54:20.162Z : Play event listener saw ♦K from 37, so it fetched /table/214/four-hands and /table/214/handaction-summary-status 214:348:21
2024-09-22T18:54:21.217Z : Play event listener saw ♥T from 32, so it fetched /table/214/four-hands and /table/214/handaction-summary-status 214:348:21
2024-09-22T18:54:22.294Z : Play event listener saw ♥Q from 10, so it fetched /table/214/four-hands and /table/214/handaction-summary-status 214:348:21
2024-09-22T18:54:23.360Z : Play event listener saw ♣A from 37, so it fetched /table/214/four-hands and /table/214/handaction-summary-status 214:348:21
2024-09-22T18:54:48.565Z : Play event listener saw ♥9 from 10, so it fetched /table/214/four-hands and /table/214/handaction-summary-status 214:348:21
2024-09-22T18:54:48.769Z : Play event listener saw ♥J from 31, so it fetched /table/214/four-hands and /table/214/handaction-summary-status 214:348:21
2024-09-22T18:54:49.859Z : Play event listener saw ♦9 from 37, so it fetched /table/214/four-hands and /table/214/handaction-summary-status 214:348:21
```

At this point, I cannot tell if the problem is still happening!  I've played a couple of hands and they've seemed OK.

I guess I will have the "played a card" event include the play ID -- those are small integers, and should increase monotonically; perhaps the bot or even the browser could check that IDs in the events are themselves monotonically increasing, and holler if not.  That'd at least draw my attention if the problem comes up again.
