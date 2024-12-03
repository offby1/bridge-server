# Why is hosting so hard?

Yes, I got <https://teensy.info> working on my own, but it was a pain in the ass.  And yes, I could probably more or less duplicate what it does.  But surely there's something easier and more out-of-the box out there somewhere?

In particular, I'm grumpy about getting an SSL certificate and rigging up the HTTP reverse proxy to use it.  Surely there are hosting providers that

* make this easy
* specialize in Django

## Random ideas

- Now that I've gotten this reasonably containerized, maybe I should read about those "run your container" services -- pretty sure AWS and Azure have those.  E.g., in a perfect world, I'd sign up for the service, they'd give me some sort of credential and URL; I'd type "docker context mumble something credential URL", and then just "docker compose up" should push the containers onto their hosting and Bob's my uncle.

In the below, ✘ means "this sucks; no need to investigate further"

## Research I've done

[The obvious search](https://duckduckgo.com/?q=django+hosting).  As expected, most of the results look scammy.

### [Tailscale](https://login.tailscale.com/admin/machines)
They don't *host*, but they do have a dead-easy [TLS-doing reverse proxy](https://tailscale.com/kb/1223/funnel#establishing-an-encrypted-proxy), which [I'm using now](https://teensy-info.tail571dc2.ts.net/) (and also [here](https://laptop.tail571dc2.ts.net/)).

I'd feel a little better about their reverse proxy if they charged me money for using it.  The blurb about it says

* it's in beta
* > Traffic sent over a Funnel is subject to non-configurable bandwidth limits.

Something I read somewhere suggested that the reverse proxy is *not* doing crypto stuff, which is good -- that means it's not working as hard as I'd feared, and thus is likely to *keep* working :-)

### digital ocean

[Use an Existing Domain](https://docs.digitalocean.com/products/networking/load-balancers/how-to/ssl-termination/#use-an-existing-domain) says

> If you manage your domain with DigitalOcean DNS, you can choose the Let’s Encrypt option to create a new, fully-managed SSL certificate. We create and automatically renew this certificate for you.

### [AWS Elastic Beanstalk](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/Welcome.html)
Clearly intends to do *something* like what I want.
I tried it once many years ago, and fled in terror; but maybe it's better now (or I'm smarter).

### [AWS Elastic Container Service](https://aws.amazon.com/ecs/)
[Here](https://www.docker.com/blog/docker-compose-from-local-to-amazon-ecs/) is a shockingly-badly written overview of how to use ECS as a docker context.

The docker docs to which it points are "retired" :-(

### [dokku](https://dokku.com/docs/networking/proxies/caddy/)

As mentioned by "boxed" on discord.  Looks interesting.

* They support "caddy" which I know has built-in ssl-cert-snagging.

### Heroku

* The "python buildpack" doesn't know what to do with poetry
* Unclear if they help with TLS at all
* Unclear if they will let me use `daphne`, somewhere I read that I gotta use `gunicorn`
  * [this](https://stackoverflow.com/a/43746621/20146) suggests it's doable
  * [this blog post from 2016?](https://blog.heroku.com/in_deep_with_django_channels_the_future_of_real_time_apps_in_django) also suggests it's doable

### [Vercel](https://vercel.com/templates/python/django-hello-world)

[Looks like](https://vercel.com/docs/projects/domains/working-with-ssl) they take care of TLS for you, somehow.

### [PythonAnywhere](https://help.pythonanywhere.com/pages/DeployExistingDjangoProject/)

[asgi support is "experimental"](https://help.pythonanywhere.com/pages/ASGIAPI/)

### [Render](https://docs.render.com/deploy-django)

Mentions uvicorn, which *might* work for me.

### Roll my own with [caddy](https://hub.docker.com/_/caddy)
I otta be able to make a simple docker-compose that includes a caddy image, and a django image (and well ok maybe also a postgresql image if I feel like using that).

### [Traefik](https://doc.traefik.io/traefik/https/overview/)
I think this is a reverse-proxy-and-lets-encrypt-client rolled into one.  I doubt they offer hosting.
"theepic.dev" on Discord (visible as Pat in the Django server) uses it.

[Cookiecutter Django](https://cookiecutter-django.readthedocs.io/en/latest/3-deployment/deployment-with-docker.html#understanding-the-docker-compose-setup) uses it.

### [Fly.io](https://fly.io/docs/django/getting-started/existing/)

I originally ruled it out because
> Doesn't mention ASGI; that term doesn't appear in their search, nor does "uvicorn" nor "daphne".

but on second thought, they do [deploy from an existing Dockerfile](https://fly.io/docs/languages-and-frameworks/dockerfile/), and offer postgres and redis as services; so they might be able to handle this.

### [google cloud run](https://cloud.google.com/run/docs/overview/what-is-cloud-run)

No persistent state; you gotta use one of their other services for that.

> To persist files permanently, you can integrate with Cloud Storage or mount a network filesystem (NFS).

### I asked [perplexity.ai](https://www.perplexity.ai/search/what-hosting-service-will-be-e-h_5FvBqcQs2kFoQaGB1mww)
It said basically Digital Ocean App Platform, or Heroku.  I'm pretty sure it ignored some bits of my question, like Poetry.
## Deployment automation ideas
### [This](https://containrrr.dev/watchtower/introduction/) might make deployment easier
It appears to be a container that polls the docker image registry, and restarts another container if it finds updates.
### Github actions (and gitlab's equivalent)
I know shockingly little about these but they're the obvious choice.
