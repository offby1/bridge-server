from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class Player:
    name: str
    partner: Player | None = None

    def __str__(self):
        return self.name


def describe_partnership(*, subject: Player, as_viewed_by: Player) -> str:
    if subject.partner is None:
        rv = f"Hi, {as_viewed_by}! "
        if subject == as_viewed_by:
            rv += f"You ({subject}) have no partner"
        else:
            rv += f"{subject} has no partner"
        return rv

    words = [f"Hi, {as_viewed_by}!"]
    if subject == as_viewed_by:
        words.append(f"Your ({subject}'s)")
    else:
        words.append(str(subject) + "'s")
    words.append("partner is")
    if subject.partner == as_viewed_by:
        words.append(f"gosh, you ({as_viewed_by})")
    else:
        words.append(str(subject.partner))

    return " ".join(words)


solo = Player(name="solo")
bob = Player(name="bob")
kim = Player(name="kim", partner=bob)
bob.partner = kim

print(describe_partnership(subject=kim, as_viewed_by=kim))
print(describe_partnership(subject=kim, as_viewed_by=bob))
print(describe_partnership(subject=kim, as_viewed_by=solo))

print(describe_partnership(subject=bob, as_viewed_by=kim))
print(describe_partnership(subject=bob, as_viewed_by=bob))
print(describe_partnership(subject=bob, as_viewed_by=solo))

print(describe_partnership(subject=solo, as_viewed_by=kim))
print(describe_partnership(subject=solo, as_viewed_by=bob))
print(describe_partnership(subject=solo, as_viewed_by=solo))
