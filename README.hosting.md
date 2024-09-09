# Why is hosting so hard?

Yes, I got <https://teensy.info> working on my own, but it was a pain in the ass.  And yes, I could probably more or less duplicate what it does.  But surely there's something easier and more out-of-the box out there somewhere?

In particular, I'm grumpy about getting an SSL certificate and rigging up the HTTP reverse proxy to use it.  Surely there are hosting providers that

* make this easy
* specialize in Django

✘ means "this sucks; no need to investigate further"

## Research I've done

[The obvious search](https://duckduckgo.com/?q=django+hosting).  As expected, most of the results look scammy.

### [Tailscale](https://login.tailscale.com/admin/machines)
They don't *host*, but they do have a dead-easy TLS-doing reverse proxy, which [I'm using now](https://teensy-info.tail571dc2.ts.net/).
### digital ocean

[Use an Existing Domain](https://docs.digitalocean.com/products/networking/load-balancers/how-to/ssl-termination/#use-an-existing-domain) says

> If you manage your domain with DigitalOcean DNS, you can choose the Let’s Encrypt option to create a new, fully-managed SSL certificate. We create and automatically renew this certificate for you.

### [AWS Elastic Beanstalk](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/Welcome.html)
Clearly intends to do *something* like what I want.
I tried it once many years ago, and fled in terror; but maybe it's better now (or I'm smarter).

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

### ✘[Fly.io](https://fly.io/docs/django/getting-started/existing/)

Doesn't mention ASGI; that term doesn't appear in their search, nor does "uvicorn" nor "daphne".
### ✘ google cloud

Bleah.
