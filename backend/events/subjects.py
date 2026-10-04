from collections.abc import Sequence


_MAX_EVENTS = 32


def validate_events(value: object) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("events must be a sequence of NATS subjects")
    if not value or len(value) > _MAX_EVENTS:
        raise ValueError("events must contain between 1 and 32 subjects")

    subjects: list[str] = []
    for subject in value:
        if not isinstance(subject, str) or not subject:
            raise ValueError("each event subject must be a nonempty string")
        if any(character.isspace() for character in subject):
            raise ValueError("NATS subjects cannot contain whitespace")
        tokens = subject.split(".")
        if any(not token for token in tokens):
            raise ValueError("NATS subjects cannot contain empty tokens")
        for index, token in enumerate(tokens):
            if "*" in token and token != "*":
                raise ValueError("the * wildcard must occupy a complete token")
            if ">" in token and (token != ">" or index != len(tokens) - 1):
                raise ValueError("> must be the final complete token")
        if subject in subjects:
            raise ValueError("event subjects must be distinct")
        subjects.append(subject)
    return tuple(subjects)
