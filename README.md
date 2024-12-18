# Wassup homies

## Getting prerequistes &c

### just
- $ `curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/.local/bin`
  $ `PATH=$PATH:$HOME/.local/bin`
  Yeah, I hate `curl | sh` too, but there doesn't seem to be any other foolproof way.
  Take a look at <https://just.systems/man/en/chapter_4.html> for other options.

### git
- $ `sudo apt install git`

### docker
- $ `sudo apt install docker.io`
- add yourself to the docker group: "sudo vigr" and then "sudo vigr -s"

### pre-commit
Optional but slick.

### pipx
- `sudo apt install pipx`

### poetry
- `pipx install poetry`

### libpq
- $ `sudo apt install libpq5`

## Running it
`just runme` will start just the web server.  DEPLOYMENT_ENVIRONMENT will be `"development"`.
`just bot` will run the bot.

`just dcu` will bring up the docker-compose stack, which includes the web server, bot, and who knows what-all else.  It conflicts with `just runme` since they both try to listen on the same port.
DEPLOYMENT_ENVIRONMENT will be `"staging"` on the laptop, and `"production"` elsewhere.  When running on the laptop, you can fool it into thinking it's production by invoking e.g. `DJANGO_SETTINGS_MODULE=project.prod_settings HOSTNAME=yeah.im.production.trustme just dcu`

## Thoughts about state

So ... I never put a lot of thought into what, exactly, should live in the db; and of that stuff, what should be immutable.

Despite whatever code I've written up to this point, I think:

* django auth stuff -- usernames, passwords, &c.  That should be mutable to the point that people can change their usernames, passwords, email addresses.

* *history* -- which players did what, and in what order.  This should be append-only.

  * when four players join at a "table" -- which might not need to be a first-class model -- that should get recorded as the first entry in some record.
    * the record should include which cards got dealt to which player
  * when any player makes a legal call, that gets appended.
  * when any player makes a legal play, that gets appended.
  * when any player abandons a table, that gets appended.
  * and uh maybe that's it?

  Figuring out the current state of a player would mean finding their most recent action:
  * if there aren't any, they're in the lobby.
  * if the most-recent action was to abandon a table, they're in the lobby.
  * otherwise they're at the table indicated by the action
    * in which case we need to replay all the actions at the table -- there won't be all that many -- to see what cards he holds, whose turn it is to do what, &c

## ponder these

* Imagine you sign up, and log in; now

  * how do you get to a table?
  * What if no table exists?

* Imagine you're in the middle of a hand.
  * How do you find out that someone at the table has made a call or a play?
    Ideally, your web page should just update without you having to do anything (and if it's your turn, it should beep at you or something).  We're probably gonna hafta use web sockets.

* what if some of the players are your table are bots, not humans?  How do they make the game advance?
  Probably the best thing is for them to be essentially separate processes, and they send their calls and plays to the server roughly the same way actual humans do.

* How will one player choose other players with whom to form a table?
  What if they want some robots instead of real players?
  What if Bob wants to play at the same table as Alice, but Alice doesn't want to play at the same table as Bob?
  How does Alice indicate that she wants to be Bob's partner?
  Those two problems seem similar: forming a partnership should be mutual, and forming a table from two partnerships should also be mutual

### Idea about async updates from the server

(I asked this [on discord](https://discord.com/channels/856567261900832808/1268956759037579325))

I've had this idea for ages; it isn't specific to this app, but this app is a good example:

Most web apps are roughly interfaces to a database (that's why Django and similar frameworks are popular).

Most such apps have more than one process interacting with them at a time.  For example, while I'm staring at my gmail inbox, some process in Google-land is able to drop new emails into it at any time.

In such cases, it'd be *really nice* for my browser's view to immediately update whenever the database changes (in a way that's relevant to whatever I'm looking at).  For example, if I am looking at my gmail inbox when a new mail arrives, my browser simply updates to display it.  That's nice!

But *most* apps don't update like that, presumably because doing so is kinda hard.  I imagine it requires websockets or something similar.

Anyhoo, I wish there were a reasonably-generic way for a given web page, whose data is populated by a db query, to tell the server "You know that query you just did on my behalf?  Well, keep me updated asynchronously whenever its results change, so I don't have to periodically re-run the query to keep up-to-date".

There's gotta be some django plugin that does this, eh?

- <https://channels.readthedocs.io/en/latest/introduction.html> might be helpful here, although I bet it doesn't automatically handle the "the db just changed" stuff for me.
  OTOH it seems to easily handle "send a message from server to browser once in a while"

- [another search site](https://djangopackages.org/search/?q=chat)

- <https://www.django-unicorn.com/> maybe.
  <https://www.django-unicorn.com/docs/#full-stack-framework-python-packages> lists a bunch of other projects.
  I poked at this a little, and it seems likely that it'd solve my problem; but I wasn't able to figure out how.
  I should probably create a separate example project solely to futz around with it.

- Perhaps a combo of <https://github.com/fanout/django-eventstream> and <https://django-pgtrigger.readthedocs.io/en/4.11.1/>
  Lower-level, but perhaps (for that reason) easier to understand.

- [htmx](https://htmx.org/server-examples/#django) says it does web-socket-y stuff too

- [sockpuppet](https://sockpuppet.argpar.se/) might but it looks awfully complex
