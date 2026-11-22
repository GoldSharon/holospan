from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BootstrapAllowlist:
    entries: frozenset[tuple[str, str]]

    @classmethod
    def parse(cls, raw: str) -> "BootstrapAllowlist":
        entries: set[tuple[str, str]] = set()
        for item in raw.split(","):
            value = item.strip()
            if not value:
                continue
            issuer, separator, subject = value.partition("|")
            if separator and issuer and subject:
                entries.add((issuer, subject))
        return cls(frozenset(entries))

    def matches(self, issuer: str, subject: str) -> bool:
        return (issuer, subject) in self.entries
