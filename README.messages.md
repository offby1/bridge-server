# Inventory of django eventstream messages that I send

| content                              | sender                                          | recipient channel    | notes                                            |
|--------------------------------------|-------------------------------------------------|----------------------|--------------------------------------------------|
| json: table, player, call            | handrecord.add_call_from_player                 | table.pk, all-tables | at every call                                    |
| json: table, contract, contract_text | handrecord.add_call_from_player                 | table.pk, all-tables | only once per table                              |
| json: table, player, card            | handrecord.add_play_from_player                 | table.pk, all-tables |                                                  |
| arbitrary html                       | models.player                                   | lobby, partnerships  | partnership created or destroyed                 |
| json: table, seats, action           | table.TableManager.create_with_two_partnerships | all-tables           | action is "just formed"                          |
| arbitrary html                       | lobby.send_lobby_message                        | lobby                | I don't think anyone listens for these           |
| arbitrary                            | player.send_player_message                      | player1:player2      | private chat                                     |
| json: table, direction, action       | table.poke_de_bot                               | all-tables           | action is "pokey pokey"; hack to wake up the bot |
