I was controlling hand 31; the others are bots.

Note how in both logs for me playing a hand, the previous log -- from "someone else" -- arrived *just before*.

```
2024-09-22T18:54:17.749Z : Play event listener saw ♠A from 32, so it fetched /table/214/four-hands and /table/214/handaction-summary-status 214:348:21
2024-09-22T18:54:17.937Z : Play event listener saw ♠9 from 31, so it fetched /table/214/four-hands and /table/214/handaction-summary-status 214:348:21
2024-09-22T18:54:19.016Z : Play event listener saw ♠6 from 10, so it fetched /table/214/four-hands and /table/214/handaction-summary-status 214:348:21
2024-09-22T18:54:20.162Z : Play event listener saw ♦K from 37, so it fetched /table/214/four-hands and /table/214/handaction-summary-status 214:348:21
2024-09-22T18:54:21.217Z : Play event listener saw ♥T from 32, so it fetched /table/214/four-hands and /table/214/handaction-summary-status 214:348:21
2024-09-22T18:54:22.294Z : Play event listener saw ♥Q from 10, so it fetched /table/214/four-hands and /table/214/handaction-summary-status 214:348:21
2024-09-22T18:54:23.360Z : Play event listener saw ♣A from 37, so it fetched /table/214/four-hands and /table/214/handaction-summary-status 214:348:21
2024-09-22T18:54:48.565Z : Play event listener saw ♥9 from 10, so it fetched /table/214/four-hands and /table/214/handaction-summary-status 214:348:21
2024-09-22T18:54:48.769Z : Play event listener saw ♥J from 31, so it fetched /table/214/four-hands and /table/214/handaction-summary-status 214:348:21
2024-09-22T18:54:49.859Z : Play event listener saw ♦9 from 37, so it fetched /table/214/four-hands and /table/214/handaction-summary-status 214:348:21
```

Is this better?  I dunno, maybe I should insist that I, the human, get to play (I was the dummy, and the declarer was a bot, so the bot played the hand)

Auction event listener saw {"table": 219, "player": 10, "call": "Pass"} 219:465:17
Auction event listener fetched /table/219/auction 219:469:25
Auction event listener fetched /table/219/bidding-box 219:471:29
Auction event listener saw {"table": 219, "player": 37, "call": "1\u2663"} 219:465:17
Auction event listener fetched /table/219/auction 219:469:25
Auction event listener fetched /table/219/bidding-box 219:471:29
Auction event listener saw {"table": 219, "player": 31, "call": "Pass"} 219:465:17
Auction event listener fetched /table/219/auction 219:469:25
Auction event listener fetched /table/219/bidding-box 219:471:29
Auction event listener saw {"table": 219, "player": 32, "call": "Pass"} 219:465:17
Auction event listener fetched /table/219/auction 219:469:25
Auction event listener fetched /table/219/bidding-box 219:471:29
Auction event listener saw {"table": 219, "player": 10, "call": "Pass"} 219:465:17
Auction event listener saw {"table": 219, "contract_text": "one Club played by      aaron, sitting North", "contract": {"opening_leader": 2}} 219:465:17
Opening lead event listener saw {"table": 219, "contract_text": "one Club played by      aaron, sitting North", "contract": {"opening_leader": 2}} 219:491:17
Auction event listener fetched /table/219/auction 219:469:25
Auction event listener fetched /table/219/bidding-box 219:471:29
2024-09-22T19:52:23.940Z : Play event listener saw ♦3 from 31, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:24.223Z : Play event listener saw ♦Q from 32, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:24.506Z : Play event listener saw ♣K from 10, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:24.825Z : Play event listener saw ♦2 from 37, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:25.115Z : Play event listener saw ♣Q from 10, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:25.353Z : Play event listener saw ♣7 from 37, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:25.669Z : Play event listener saw ♣3 from 31, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:25.983Z : Play event listener saw ♣A from 32, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:26.258Z : Play event listener saw ♦6 from 32, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:26.544Z : Play event listener saw ♠Q from 10, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:26.843Z : Play event listener saw ♦7 from 37, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:27.122Z : Play event listener saw ♦K from 31, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:27.420Z : Play event listener saw ♥3 from 31, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:27.706Z : Play event listener saw ♥7 from 32, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:27.991Z : Play event listener saw ♥2 from 10, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:28.300Z : Play event listener saw ♥9 from 37, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:28.568Z : Play event listener saw ♠9 from 37, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:28.857Z : Play event listener saw ♠A from 31, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:29.150Z : Play event listener saw ♠5 from 32, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:29.441Z : Play event listener saw ♠3 from 10, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:29.747Z : Play event listener saw ♠7 from 31, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:30.031Z : Play event listener saw ♦A from 32, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:30.318Z : Play event listener saw ♠2 from 10, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:30.657Z : Play event listener saw ♠K from 37, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:30.717Z : Play event listener saw ♠6 from 37, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:31.231Z : Play event listener saw ♠J from 31, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:31.525Z : Play event listener saw ♥T from 32, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:31.815Z : Play event listener saw ♠T from 10, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:32.108Z : Play event listener saw ♥4 from 31, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:32.406Z : Play event listener saw ♥K from 32, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:32.721Z : Play event listener saw ♥8 from 10, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:33.008Z : Play event listener saw ♥J from 37, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:33.283Z : Play event listener saw ♦T from 32, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:33.570Z : Play event listener saw ♥A from 10, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:33.833Z : Play event listener saw ♦8 from 37, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:34.169Z : Play event listener saw ♥Q from 31, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:34.472Z : Play event listener saw ♦4 from 32, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:34.735Z : Play event listener saw ♣T from 10, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:35.012Z : Play event listener saw ♦J from 37, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:35.343Z : Play event listener saw ♣8 from 31, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:35.422Z : Play event listener saw ♣6 from 10, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:35.938Z : Play event listener saw ♣9 from 37, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:36.248Z : Play event listener saw ♣J from 31, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:36.571Z : Play event listener saw ♣2 from 32, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:36.638Z : Play event listener saw ♠4 from 31, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:37.186Z : Play event listener saw ♦9 from 32, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:37.477Z : Play event listener saw ♣4 from 10, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:37.797Z : Play event listener saw ♠8 from 37, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:37.859Z : Play event listener saw ♣5 from 10, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:38.357Z : Play event listener saw ♥5 from 37, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:38.664Z : Play event listener saw ♥6 from 31, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
2024-09-22T19:52:38.998Z : Play event listener saw ♦5 from 32, so it fetched /table/219/four-hands and /table/219/handaction-summary-status 219:503:21
