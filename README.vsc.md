I have never gotten Visual Studio Code working reliably with this project, but I'm gonna invest some time and try.

I'll take notes here about what I did, in case I *do* get it working, and the steps in so doing are complex enough that I don't remember them.

* Start by wiping out everything:

  `just nuke && docker-nuke`
  `rm -rfv "$HOME/Library/Application Support/Code" ~/.vscode`

* Run it :-)

    - dismiss the "welcome" tab
    - Command-o, open this folder
    - "Yes, I trust the authors"
    - again dismiss the "welcome" tab

* Find some extensions?

    All right, now what ... I searched for "django" in the Extensions Marketplace.
    Got lots of hits, sorted with the most-installed ones first.
      Name: Django
      Id: batisteo.vscode-django
    looks reasonable; let's try it ... it installed so quickly, and didn't appear to install the Python extension, that I suspect it doesn't do much of use.

    - searching for `site:https://awesomedjango.org/ "visual studio code"` gives literally nothing
    - https://djangopackages.org/ similarly
    - https://djangocentral.com/visual-studio-code-setup-for-django-developers/ is relevant but seems very old
    - https://learn.microsoft.com/en-us/visualstudio/python/learn-django-in-visual-studio-step-01-project-and-solution?view=vs-2022 is *Visual Studio*, which, ha ha, is not the same as *Visual Studio Code*

* Just follow MS' own instructions

    - https://github.com/Microsoft/vscode-docs/blob/main/docs/python/tutorial-django.md looks more relevant
      It seems to say that I merely need
      - install the Python extension
      - do some simple and obvious fiddling in the terminal (I can probably do `poetry install`)
      - select the .venv via `Python: Select Interpreter`
      - crucially: [create the launch.json file] (https://github.com/Microsoft/vscode-docs/blob/main/docs/python/tutorial-django.md#create-a-debugger-launch-profile).  I've probably never done this; perhaps this is all that I was missing?

    OK I've done the above; the tutorial says that I should see "Django" as one of the debugging options, but all I see are `Node.js`, `Python Debugger`, and two flavors of `Web App`

    Ah it's a braino in their docs: I have to choose `Python Debugger` and *then* I get the chance to choose `Django`.

    So far the above has kinda worked, but
    - I had to take some moderately complex steps that I haven't yet written down -- I think I ran "poetry install" in the VSC terminal, but also ran "just runme" or something outside of it, to get various dependencies working (like running the database)
    - istr that the browser was getting 404s on static files, no idea why or how
