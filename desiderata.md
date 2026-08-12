# Desiderata

**All of this has been built.** See `docs/README.google-oauth.md` for what shipped,
`docs/SETUP.google-oauth.md` for how to configure it. Kept because it records what I asked
for, and why.

---

I'd like the `/signup/` page to offer to create accounts to which one can login using one's gmail credentials, in
addition to the current accounts which authenticate with username and password.

I'd like it to be conventional: similar to many other websites that do this.

When creating an account that uses gmail, the user should continue to be given the chance to choose a short username; that's so that they don't have to expose their email address to everyone who looks at this site.

Of course, I also want the `/accounts/login/` page to offer a "log in with google" button.

---

One note on how it turned out: we went further than the last point asked for. We never
request the email address from Google at all — the requested scope is `profile` only — so
there is no address in the database to expose, rather than one we take care not to display.
