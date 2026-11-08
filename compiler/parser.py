
from lexer import lex, ToyError
from ast_nodes import *


class Parser:
    def __init__(self, source_code: str):
        self.tokens = lex(source_code)
        self.position = 0

    # ---------- looking at tokens ----------
    def current_token(self):
        """The token we are looking at (does not consume it)."""
        return self.tokens[self.position]

    def look_ahead(self, offset=1):
        """A later token, without consuming anything."""
        index = min(self.position + offset, len(self.tokens) - 1)
        return self.tokens[index]

    def consume_token(self):
        """Return the current token and move to the next one."""
        consumed_token = self.current_token()
        if consumed_token.kind != "eof":
            self.position += 1
        return consumed_token

    # ---------- checking what we have ----------
    def is_operator(self, symbol: str) -> bool:
        """True if the current token is the operator `symbol`."""
        token = self.current_token()
        return token.kind == "operator" and token.value == symbol

    def is_keyword(self, word: str) -> bool:
        """True if the current token is the keyword `word`."""
        token = self.current_token()
        return token.kind == "keyword" and token.value == word

    # ---------- consuming what we expect ----------
    def match_operator(self, symbol: str) -> bool:
        """If the current token is `symbol`, consume it and return True.
        Otherwise do nothing and return False."""
        if self.is_operator(symbol):
            self.consume_token()
            return True
        return False

    def expect_operator(self, symbol: str):
        """Consume `symbol` and return its token, or raise an error."""
        if self.is_operator(symbol):
            return self.consume_token()
        self.error(f"expected '{symbol}', found {self.describe_current_token()}")

    def expect_keyword(self, word: str):
        """Consume the keyword `word` and return its token, or raise an error."""
        if self.is_keyword(word):
            return self.consume_token()
        self.error(f"expected '{word}', found {self.describe_current_token()}")

    def expect_identifier(self):
        """Consume any identifier and return its token, or raise an error."""
        if self.current_token().kind == "identifier":
            return self.consume_token()
        self.error(f"expected an identifier, found {self.describe_current_token()}")

    # ---------- errors ----------
    def describe_current_token(self) -> str:
        """Text for error messages."""
        token = self.current_token()
        if token.kind == "eof":
            return "end of file"
        return f"'{token.value}'"

    def error(self, message: str):
        token = self.current_token()
        raise ToyError(message, token.line, token.column)

    # ---------- types ----------
       # ---------- types ----------
    def parse_base_type(self):
        """base_type = 'int' | 'bool' | IDENTIFIER      (sans crochets)"""
        token = self.current_token()
        is_builtin_type = token.kind == "keyword" and token.value in ("int", "bool")
        is_struct_name = token.kind == "identifier"
        if is_builtin_type or is_struct_name:
            self.consume_token()
            return TypeRef(token.value, line=token.line, column=token.column)
        self.error(f"expected a type, found {self.describe_current_token()}")

    def parse_type(self):
        """type = base_type { '[' ']' }"""
        type_ref = self.parse_base_type()
        while self.match_operator("["):
            self.expect_operator("]")
            type_ref.dimension_count += 1
        return type_ref
