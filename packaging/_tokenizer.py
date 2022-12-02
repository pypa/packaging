import re
from typing import Dict, Generator, NoReturn, Optional

from .specifiers import Specifier


class Token:
    def __init__(self, name: str, text: str, position: int) -> None:
        self.name = name
        self.text = text
        self.position = position

    def matches(self, name: str = "") -> bool:
        if name and self.name != name:
            return False
        return True


class ParseExceptionError(Exception):
    """
    Parsing failed.
    """

    def __init__(self, message: str, position: int) -> None:
        super().__init__(message)
        self.position = position


DEFAULT_RULES = {
    "LPAREN": r"\s*\(",
    "RPAREN": r"\s*\)",
    "LBRACKET": r"\s*\[",
    "RBRACKET": r"\s*\]",
    "SEMICOLON": r"\s*;",
    "COMMA": r"\s*,",
    "QUOTED_STRING": re.compile(
        r"""
            \s*
            (
                ('[^']*')
                |
                ("[^"]*")
            )
        """,
        re.VERBOSE,
    ),
    "OP": r"\s*(===|==|~=|!=|<=|>=|<|>)",
    "BOOLOP": r"\s*(or|and)",
    "IN": r"\s*in",
    "NOT": r"\s*not",
    "VARIABLE": re.compile(
        r"""
            \s*
            (
                python_version
                |python_full_version
                |os[._]name
                |sys[._]platform
                |platform_(release|system)
                |platform[._](version|machine|python_implementation)
                |python_implementation
                |implementation_(name|version)
                |extra
            )
        """,
        re.VERBOSE,
    ),
    "VERSION": re.compile(Specifier._version_regex_str, re.VERBOSE | re.IGNORECASE),
    "URL_SPEC": r"\s*@ *[^ ]+",
    "IDENTIFIER": r"\s*[a-zA-Z0-9._-]+",
}


class Tokenizer:
    """Stream of tokens for a LL(1) parser.

    Provides methods to examine the next token to be read, and to read it
    (advance to the next token).
    """

    next_token: Optional[Token]

    def __init__(self, source: str, rules: Dict[str, object] = DEFAULT_RULES) -> None:
        self.source = source
        self.rules = {name: re.compile(pattern) for name, pattern in rules.items()}
        self.next_token = None
        self.generator = self._tokenize()
        self.position = 0

    def peek(self) -> Token:
        """
        Return the next token to be read.
        """
        if not self.next_token:
            self.next_token = next(self.generator)
        return self.next_token

    def match(self, name: str) -> bool:
        """
        Return True if the next token matches the given arguments.
        """
        token = self.peek()
        return token.matches(name)

    def expect(self, name: str, error_message: str) -> Token:
        """
        Raise SyntaxError if the next token doesn't match given arguments.
        """
        token = self.peek()
        if not token.matches(name):
            raise self.raise_syntax_error(message=error_message)
        return token

    def read(self, name: str, error_message: str = "") -> Token:
        """Return the next token and advance to the next token.

        Raise SyntaxError if the token doesn't match.
        """
        result = self.expect(name, error_message=error_message)
        self.next_token = None
        return result

    def try_read(self, name: str) -> Optional[Token]:
        """read() if the next token matches the given arguments.

        Do nothing if it does not match.
        """
        if self.match(name):
            return self.read(None)
        return None

    def raise_syntax_error(self, *, message: str) -> NoReturn:
        """
        Raise SyntaxError at the given position in the marker.
        """
        at = f"at position {self.position}:"
        marker = " " * self.position + "^"
        raise ParseExceptionError(
            f"{message}\n{at}\n    {self.source}\n    {marker}",
            self.position,
        )

    def _make_token(self, name: str, text: str) -> Token:
        """
        Make a token with the current position.
        """
        return Token(name, text, self.position)

    def _tokenize(self) -> Generator[Token, Token, None]:
        """
        The main generator of tokens.
        """
        while self.position < len(self.source):
            for name, expression in self.rules.items():
                match = expression.match(self.source, self.position)
                if match:
                    token_text = match[0]

                    yield self._make_token(name, token_text.strip())
                    self.position += len(token_text)
                    break
            else:
                raise self.raise_syntax_error(message="Unrecognized token")
        yield self._make_token("END", "")
