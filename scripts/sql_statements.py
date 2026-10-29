"""Parse MySQL statements while preserving quoted semicolons."""

from __future__ import annotations

import re

_DELIMITER_DIRECTIVE = re.compile(r"[ \t]*DELIMITER[ \t]+([^\s]+)[ \t]*(?:\r?\n|$)", re.I)


def split_sql(text: str) -> list[str]:
    # Kept cohesive because SQL quoting, comments, and delimiters share one scanner state.
    statements: list[str] = []
    buffer: list[str] = []
    quote: str | None = None
    escaped = False
    comment = False
    delimiter = ";"
    index = 0
    while index < len(text):
        if not quote and not comment and (index == 0 or text[index - 1] in "\r\n"):
            directive = _DELIMITER_DIRECTIVE.match(text, index)
            if directive:
                if "".join(buffer).strip():
                    raise ValueError("DELIMITER changed before the current statement ended")
                delimiter = directive[1]
                index = directive.end()
                continue
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
        elif text.startswith(delimiter, index):
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
            index += len(delimiter) - 1
        else:
            buffer.append(character)
        index += 1
    trailing = "".join(buffer).strip()
    if trailing:
        statements.append(trailing)
    return statements
