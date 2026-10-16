from dataclasses import dataclass

KEYWORDS = {"struct", "fun", "var", "if", "else", "while", "return",
            "print", "new", "null", "true", "false", "int", "bool"}
TWO_CHAR_OPERATORS = {"==", "!=", "<=", ">=", "&&", "||"}
ONE_CHAR_OPERATORS = set("+-*/%<>=!(){}[];:,.")


class ToyError(Exception):
    def __init__(self, message, line, column):
        super().__init__(f"{line}:{column}: {message}")


@dataclass
class Token:
    kind: str      # 'integer' | 'identifier' | 'keyword' | 'operator' | 'eof'
    value: object
    line: int
    column: int


def lex(source_code: str):
    tokens = []
    index, line, column = 0, 1, 1

    while index < len(source_code):
        current_char = source_code[index]

        if current_char == "\n":
            line += 1
            column = 1
            index += 1

        elif current_char in " \t\r":
            index += 1
            column += 1

        elif source_code.startswith("//", index):
            while index < len(source_code) and source_code[index] != "\n":
                index += 1

        elif current_char.isdigit():
            start_index, start_column = index, column
            while index < len(source_code) and source_code[index].isdigit():
                index += 1
                column += 1
            number_text = source_code[start_index:index]
            tokens.append(Token("integer", int(number_text), line, start_column))

        elif current_char.isalpha() or current_char == "_":
            start_index, start_column = index, column
            while index < len(source_code) and (source_code[index].isalnum()
                                                or source_code[index] == "_"):
                index += 1
                column += 1
            word = source_code[start_index:index]
            kind = "keyword" if word in KEYWORDS else "identifier"
            tokens.append(Token(kind, word, line, start_column))

        elif source_code[index:index + 2] in TWO_CHAR_OPERATORS:
            operator = source_code[index:index + 2]
            tokens.append(Token("operator", operator, line, column))
            index += 2
            column += 2

        elif current_char in ONE_CHAR_OPERATORS:
            tokens.append(Token("operator", current_char, line, column))
            index += 1
            column += 1

        else:
            raise ToyError(f"unexpected character {current_char!r}", line, column)

    tokens.append(Token("eof", None, line, column))
    return tokens