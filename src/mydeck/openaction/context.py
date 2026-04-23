from dataclasses import dataclass


@dataclass(frozen=True)
class KeyContext:
    deck_serial: str
    page: str
    key: int

    def to_token(self) -> str:
        return f"{self.deck_serial}|{self.page}|{self.key}"

    @classmethod
    def from_token(cls, token: str) -> "KeyContext":
        deck, page, key = token.rsplit("|", 2)
        return cls(deck_serial=deck, page=page, key=int(key))
