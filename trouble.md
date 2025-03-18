Starting from scratch (i.e., "just drop" and "just follow"), a stress run ("just stress --min-players=20") shows fewer than three boards per table:

http://localhost:9000/hand/ shows 7 hands, not the expected 15.

```table
| Status | Tournament # | Table | Board | players                                                                          | Result                                                                            |
|--------+--------------+-------+-------+----------------------------------------------------------------------------------+-----------------------------------------------------------------------------------|
| ✔      |            1 |     1 |    13 | synthetic_prez, synthetic_freamon, synthetic_rhonda, synthetic_tilghman          | one Club played by synthetic_prez, sitting North: Made contract with 1 overtricks |
| ✔      |            1 |     2 |    13 | synthetic_bodie, synthetic_cutty, synthetic_kima, synthetic_levy                 | Passed Out                                                                        |
| ✔      |            1 |     2 |    15 | synthetic_bodie, synthetic_cutty, synthetic_kima, synthetic_levy                 | one Heart played by synthetic_cutty, sitting East: Made contract exactly          |
| ✔      |            1 |     3 |    13 | synthetic_tony gray, synthetic_butchie, synthetic_sydnor, synthetic_judge phelan | one Diamond played by synthetic_tony gray, sitting North: Made contract exactly   |
| ✔      |            1 |     4 |    13 | synthetic_randy, synthetic_wallace, synthetic_marla, synthetic_d'angelo          | Passed Out                                                                        |
| ✔      |            1 |     4 |    15 | synthetic_randy, synthetic_wallace, synthetic_marla, synthetic_d'angelo          | five Spades played by synthetic_marla, sitting South: Down 5                      |
| ✔      |            1 |     5 |    13 | synthetic_stringer, synthetic_marlo, synthetic_norman, synthetic_bunk            | three Clubs played by synthetic_marlo, sitting East: Down 4                       |
```

... also, after "just superuser", changing _prez to have a password, and logging in as him, I noticed the bots in a loop: noticing they're not seated, so exiting and trying again ... over and over.
