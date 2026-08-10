"""Parse MySQL statements while preserving quoted semicolons."""

from __future__ import annotations


def split_sql(text: str) -> list[str]:
    # Kept cohesive because SQL quoting, comments, and delimiters share one scanner state.
    statements: list[str] = []
    buffer: list[str] = []
    quote: str | None = None
    escaped = False
    comment = False
    index = 0
    while index < len(text):
        character = text[index]
        next_character = text[index + 1] if index + 1 < len(text) else ""
        if comment:
            if character in "\r\n":
                comment = False
                buffer.append(character)
        elif quote:
            buffer.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
        elif character == "-" and next_character == "-":
            comment = True
            index += 1
        elif character in "'\"`":
            quote = character
            buffer.append(character)
        elif character == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
        else:
            buffer.append(character)
        index += 1
    trailing = "".join(buffer).strip()
    if trailing:
        statements.append(trailing)
    return statements
