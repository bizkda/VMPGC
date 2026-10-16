"""Lexer for the Toy language."""
from dataclasses import dataclass

KEYWORDS = {
    "struct", "fun", "var", "if", "else", "while", "return", "print",
    "new", "null", "true", "false", "int", "bool",
}

TWO_CHAR = {"==", "!=", "<=", ">=", "&&", "||"}
ONE_CHAR = set("+-*/%<>=!(){}[];:,.")


class ToyError(Exception):
    def __init__(self, msg, line, col):
        super().__init__(f"{line}:{col}: {msg}")
        self.line, self.col = line, col


@dataclass
class Token:
    kind: str    # 'int', 'id', 'kw', 'op', 'eof'
    value: object
    line: int
    col: int

    def __repr__(self):
        return f"Token({self.kind},{self.value!r}@{self.line}:{self.col})"


def lex(src: str):
    toks, i, line, col, n = [], 0, 1, 1, len(src)

    def adv(k=1):
        nonlocal i, line, col
        for _ in range(k):
            if src[i] == "\n":
                line, col = line + 1, 1
            else:
                col += 1
            i += 1

    while i < n:
        c = src[i]
        if c in " \t\r\n":
            adv()
        elif src.startswith("//", i):
            while i < n and src[i] != "\n":
                adv()
        elif c.isdigit():
            l, cl, j = line, col, i
            while j < n and src[j].isdigit():
                j += 1
            toks.append(Token("int", int(src[i:j]), l, cl))
            adv(j - i)
        elif c.isalpha() or c == "_":
            l, cl, j = line, col, i
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            word = src[i:j]
            toks.append(Token("kw" if word in KEYWORDS else "id", word, l, cl))
            adv(j - i)
        elif src[i:i + 2] in TWO_CHAR:
            toks.append(Token("op", src[i:i + 2], line, col))
            adv(2)
        elif c in ONE_CHAR:
            toks.append(Token("op", c, line, col))
            adv()
        else:
            raise ToyError(f"unexpected character {c!r}", line, col)
    toks.append(Token("eof", None, line, col))
    return toks
