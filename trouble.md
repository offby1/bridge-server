# Oh no

The usual `just drop dcu -d && just stress --min-players=20` created a tournament of 15
hands per round, but things just stopped happening after 12 hands.  Haven't yet figured out why.

Looks like some bots are down when they should be up, and we're just sitting around waiting for them.

The bots seem to play just fine in the first round; but when the second round starts, at least some -- perhaps the ones that moved to new tables -- either don't start, or if they do start, they never "hear" any events, so they don't do anything.

## It might be easier ...

... to reason about whether the bot should be up or not if we change the rule to "the bot is down when `allow_bot_to_play_for_me` is `False`, and up otherwise"; in particular, it doesn't matter if the relevant player is seated

And it might be easier to enforce that if, instead of having calls to `_control_bot` scattered hither and thither, I used a signal, or a post-commit hook, or something like that, to check if that field changed
