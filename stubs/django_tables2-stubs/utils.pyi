class Accessor(str):
    def __new__(cls, value: str) -> "Accessor": ...

A = Accessor
