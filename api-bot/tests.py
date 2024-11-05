from apibot import dispatch_hand_action


def test_whatever():
    dispatch_hand_action(msg={}, session="You don't even look at this, do you", current_seat_pk=1)
