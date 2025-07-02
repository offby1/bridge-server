# Wot

I want to see the SQL queries made by the `call_post_view` and `play_post_view`, in order to maybe eliminate some redundant ones.

My first idea: use the django toolbar.  It *usually* does a wonderful job of just this, but afaict only works well on traditional web pages; whereas my web pages that invoke those views do so via HTMX, which complicates things.

I picked one of my unit tests, and tarted it up to sort of manually invoke the toolbar, and that works, but

* the resulting info (in particular, the stack traces of the code that invokes the queries) is in html-in-json, which seems inconvenient;
* it seems brittle (I kludged it up with the help of chatgpt, which kept getting details wrong)

So -- the next idea is to slap together a simple HTML page that just contains a form or two that invokes those views, and have the django toolbar do its magic on *that*.
