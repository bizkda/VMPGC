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
        if consumed_token.kind != "eof":    # note: != , so we stop at the end
            self.position += 1
        return consumed_token
    

    # ---------- checking what we have ----------
    def is_operator(self, symbol: str) -> bool:
        """True if the current token is the operator `symbol`."""
        if(self.tokens.kind == "operator" and self.token.value == symbol):
            return True

    def is_keyword(self, word: str) -> bool:
        if(self.tokens.kind == "keyword" and self.token.value == word):
            return True

    # ---------- consuming what we expect ----------
    def match_operator(self, symbol: str) -> bool:
        """If the current token is `symbol`, consume it and return True.
        Otherwise do nothing and return False."""
        # TODO
        pass

    def expect_operator(self, symbol: str):
        """Consume `symbol`, or raise an error if it's not there."""
        # TODO: if check_operator(symbol): return self.advance()
        #       else: self.error(f"expected '{symbol}', found {...}")
        pass

    def expect_keyword(self, word: str):
        # TODO: same idea
        pass

    def expect_identifier(self):
        """Consume an identifier token and return it."""
        # TODO: kind must be "identifier"
        pass

    # ---------- errors ----------
    def error(self, message: str):
        token = self.current()
        raise ToyError(message, token.line, token.column)