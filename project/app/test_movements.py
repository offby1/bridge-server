from app.utils.movements import make_movement, Board, Pair


def test_movements() -> None:
    a_board = Board(123)
    a_pair = Pair("hi, I'm a pair")
    m = make_movement(boards=[a_board], pairs=[a_pair])
    assert str(m) == "cat"
