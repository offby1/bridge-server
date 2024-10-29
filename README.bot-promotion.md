# Wassup

Have you noticed that there are two bots?

There's `project/app/management/commands/bot.py`, and there's `api-bot/apibot.py`.  The former has been around a while and more or less works fine; the latter is just getting close to working.

I would like to replace the old guy with the new upstart!

## Why
The new guy is intended to exercice the (new) API, which should let anyone with internet access interact with the server -- in particular, they should be able to write their own bot.  Sometimes I fantasize that I'll have a tournament, where random people on the Internet write bots, and I somehow play them against each other, and give a prize to the winner.

But why deprecate the old one?  Because I (think I) can, and because I don't want two chunks of code that do more or less the same thing.
## How
- ensure the new bot can do everything the old one does:
  - follow a player from one hand to the next
  - make calls and plays
    - note that the old bot cheats when it does this, which makes my life as a programmer easier :-)
- figure out how to make the new guy resilient:
  - if it somehow misses some server-sent events, have it refetch them at its earliest oppportunity
  - for the instances that I will run on my server, put them under the control of upstart or something to ensure they come back after the server reboots.
- come up with some mechanism to start a new api bot process every time some player enables the `allow_bot_to_play_for_me` switch.  I *assume* that having dozens of such processes is feasible.
## When

I dunno, maan; I guess once I'm convinced the api bot can do everything the old one does.
