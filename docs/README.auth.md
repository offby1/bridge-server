# How to auth


## An "allauth" branch in this repo.

Works pretty well, but it'd be nice to not require a password to get things rolling.

## A "django-passkeys" branch in this repo

hopelessly broken

## [python-social-auth](https://python-social-auth.readthedocs.io/en/latest/configuration/django.html)

Looks pretty complex at first glance

## [django-oauth-toolkit](https://django-oauth-toolkit.readthedocs.io/en/latest/)

  Haven't looked into this, but it seems to not be moribund

## [py_webauthn](https://github.com/duo-labs/py_webauthn)

as suggested by [ChatGPT](https://chatgpt.com/share/69346cfb-08cc-8013-abf6-e0f226a704fc)

## [webauthn-rp](https://webauthn-rp.readthedocs.io/en/latest/index.html)

### How I got it working

Good Lord was it a pain in the ass getting it working on Mac.

- "poetry install" failed due to some C compilation problem.
  Workaround: simply omit "typed-ast" from ... er... somewhere?  And re-do `poetry lock` then `poetry install`
- the defaults are set up to listen on localhost port 5000, but on my Mac, something called ControlCenter is already listening on that port.
  Bizarrely, when *this* app tries to listen on that same port, it doesn't get E_ADDRINUSE; it appears to work.  But the web browser seems to be connecting to ControlCenter, and getting a 403.  That one took a while to diagnose.
  The workaround: change 5000 to 6543 everywhere.
- If you invoke the code like `python -m flask --app examples.flask.app run  --host=localhost --port=6543`, that skips the database init step, so you get mysterious failures.
  The workaround: just do `python -m examples.flask.app`

### also Got it working on ubuntu 22.04 "jammy"

... but that's pointless now that I've managed to get it working on the Mac

* had to add a "with app.app_context" to the main thing
```
commit 87bfd8c0ce44c32d81175f50e14ff7b09e545e61 (HEAD -> master)
Author: Eric Hanchrow <eric.hanchrow@gmail.com>
Date:   2023-03-12 12:38:22 -0700

    Add overlooked `with app.app_context():`

diff --git a/examples/flask/app.py b/examples/flask/app.py
index ced96f8..ee70fdd 100644
--- a/examples/flask/app.py
+++ b/examples/flask/app.py
@@ -324,7 +324,8 @@ def index():

 if __name__ == '__main__':
     try:
-        db.create_all()
+        with app.app_context():
+            db.create_all()
         app.run(host='localhost', port='5000')
     finally:
         if os.path.exists(DATABASE_PATH):
```
* couldn't figure out how to forward the port it listened on, so I used ssh to do it
```
multipass info --all # to get the VM's IP address
ssh -L5000:localhost:5000 ubuntu@192.168.65.14`
```
## auth0
They're some sorta web service, which apparently I signed up for.  I haven't looked into it at all yet.

https://manage.auth0.com/dashboard/
