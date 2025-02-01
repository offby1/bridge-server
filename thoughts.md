# Onboarding!

Start with the home page when logged out.

At each page, the "next step" should be blindingly obvious -- i.e, how do I play.

## When first signed in

You need to find a partner.  It should be easy to *create* a synthetic partner (but only if there isn't one already; we don't want to allow creation of zillions of them), as well as choose an existing player.

Currently you'll see "Find swinging singles in your area", but

- that's really small and not obvious
- it won't help you create a synthetic player

## Once you've got a partner

You need to find opponents.  Again, it should be easy to *create* synthetic opponents, if there aren't already some.

## Once you've got opponents

You need to sit at a table.  We already (I think!) will create a new table in an existing tournament; and (again, I think) we already will create a new incomplete tournament if there isn't already one.

We could, but probably shouldn't, create enough synthetic players to fill up a tournament; that seems odd.  Even with just one human and three synths, the human can play a bunch of hands and get scored on each; they just won't be able to compare their play on any given board with anyone else.  And for now, anyway, even if they *could* compete against a fleet of bots, my bots play so poorly that it wouldn't tell you much about your skill.

[1] Would we ever want to *delete* synthetic players?  Maybe some periodic thing that scans them, and if there are a lot of them who haven't logged in in (say) a couple days, just nuke 'em?  What would that do to hands they'd played, though?  Maybe instead of nuking them, "deactivate" them, whatever that means (i.e,. turn off their "allow the bot to play for me", to conserve slots in the BotPlayer table)
