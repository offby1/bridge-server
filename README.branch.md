# Today's bug

https://erics-work-macbook-pro.tail571dc2.ts.net/hand/1/archive/

shows

    Board #1, Neither side vulnerable, dealt by NORTH
    one Club played by amber, sitting East

But then it also shows `52:Declarer! amy (bot) (WEST):`

Wassup?  Well, the latter comes from `card_display.West.player.name_dir` in `templates/four-hands.html`, and that method looks at the player's role in their *current* hand, as opposed to whichever hand this page is examining.
