# Why is hosting so hard?

- Now that I've gotten this reasonably containerized, maybe I should read about those "run your container" services -- pretty sure AWS and Azure have those.  E.g., in a perfect world, I'd sign up for the service, they'd give me some sort of credential and URL; I'd type "docker context mumble something credential URL", and then just "docker compose up" should push the containers onto their hosting and Bob's my uncle.

  I dimly recall investigating, and finding that there are exactly no services like this.  But a simple Unix box with docker and ssh seems to be all I need for now: I can deploy to it with a remote docker context.

In the below, ✘ means "this sucks; no need to investigate further"

## Research I've done

[The obvious search](https://duckduckgo.com/?q=django+hosting).  As expected, most of the results look scammy.

### [Serverless Container Platform](https://www.google.com/search?q=serverless+container+platform)
Never heard of it until just now; sounds kinda like what I want, maybe?
E.g., AWS Fargate, which I've heard of, but know nothing about.
### [Tailscale](https://login.tailscale.com/admin/machines)
They don't *host*, but they do have a dead-easy [TLS-doing reverse proxy](https://tailscale.com/kb/1223/funnel#establishing-an-encrypted-proxy), which I'd been using before I figured out how to get the Caddy docker image working.

### [railway.app](https://railway.app/)
Glanced at it; it clearly aims to make deployment easy.  No idea if it's got what I'd need, though; worth more investigation.

### ✘ digital ocean

The signup process *looks* slick, but kept refusing to accept my SSH public key.  Finally I gave up and switched to "log in with a password" ... then found out that it had created *four* "droplets" and *four* postgres databases (which would charge me $80/month total) without telling me (i.e., my attempts to add my ssh public key might have succeeded even though the UI said they'd fail?). Overwhelmingly untrustworthy.  I had to spend a fair amount of time individually deleting the droplets and databases, and shutting down my account.

I opened [a ticket](https://cloudsupport.digitalocean.com/s/case/500QP00000SwqJ3YAJ/please-delete-my-account-asap) begging them to delete my account.  Now I'm 100% at their mercy (I cannot find a way to detach my billing info from the account; I used Google Pay)

I got an email with some links; following one of them I was able to delete my account.  *Phew*

[Use an Existing Domain](https://docs.digitalocean.com/products/networking/load-balancers/how-to/ssl-termination/#use-an-existing-domain) says

> If you manage your domain with DigitalOcean DNS, you can choose the Let’s Encrypt option to create a new, fully-managed SSL certificate. We create and automatically renew this certificate for you.

[This page full of marketing blather](https://www.digitalocean.com/products/app-platform) suggests they target Django.

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
### [django-simple-deploy](https://django-simple-deploy.readthedocs.io/en/latest/general_documentation/choosing_platform/)
Aims to automate deployments to fly.io, heroku, and "platform.sh" (which I've never heard of until now).  Looks slick.
