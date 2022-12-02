import re
from typing import Any, Dict, Generator, NoReturn, Optional, Set, Union

from .specifiers import Specifier

TokenNameMatchT = Union[str, Set[str], Dict[str, Any]]


class Token:
    def __init__(self, name: str, text: str, position: int) -> None:
        self.name = name
        self.text = text
        self.position = position

    def matches(self, name: TokenNameMatchT = "") -> bool:
        if isinstance(name, str):
            name = {name}

        if self.name in name:
            return True

        return False


class ParseExceptionError(Exception):
    """
    Parsing failed.
    """

    def __init__(self, message: str, position: int) -> None:
        super().__init__(message)
        self.position = position


DEFAULT_RULES = {
    "LPAREN": r"\(",
    "RPAREN": r"\)",
    "LBRACKET": r"\[",
    "RBRACKET": r"\]",
    "SEMICOLON": r";",
    "COMMA": r",",
    "QUOTED_STRING": re.compile(
        r"""
            (
                ('[^']*')
                |
                ("[^"]*")
            )
        """,
        re.VERBOSE,
    ),
    "OP": "(===|==|~=|!=|<=|>=|<|>)",
    "BOOLOP": "(or|and)",
    "IN": "in",
    "NOT": "not",
    "VARIABLE": re.compile(
        r"""
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
    "URL_SPEC": "@ *[^ ]+",
    "IDENTIFIER": "[a-zA-Z0-9._-]+",
    "WS": "\\s+",
}
WHITESPACE_TOKENS = "WS"
MARKER_VAR_SUITABLE_TOKENS = {"VARIABLE", "VERSION"}
NAME_SUITABLE_TOKENS = {"IDENTIFIER", "VARIABLE", "NOT", "IN", "BOOLOP"}


class Tokenizer:
    """Stream of tokens for a LL(1) parser.

    Provides methods to examine the next token to be read, and to read it
    (advance to the next token).
    """

    next_token: Optional[Token]

    def __init__(self, source: str, rules: Dict[str, object] = DEFAULT_RULES) -> None:
        self.source = source
        self.rules = {name: re.compile(pattern) for (name, pattern) in rules.items()}
        self.next_token = None
        self.generator = self._tokenize()
        self.position = 0

    def peek(self, skip: TokenNameMatchT = WHITESPACE_TOKENS) -> Token:
        """
        Return the next token to be read.
        """
        while not self.next_token:
            self.next_token = next(self.generator)
            if self.next_token and self.next_token.matches(skip):
                # print("skip", self.next_token)
                self.next_token = None
        # print("peek", self.next_token)
        return self.next_token

    def match(
        self, name: TokenNameMatchT, skip: TokenNameMatchT = WHITESPACE_TOKENS
    ) -> bool:
        """
        Return True if the next token matches the given arguments.
        """
        token = self.peek(skip)
        return token.matches(name)

    def expect(
        self,
        name: TokenNameMatchT,
        error_message: str,
        skip: TokenNameMatchT = WHITESPACE_TOKENS,
    ) -> Token:
        """
        Raise SyntaxError if the next token doesn't match given arguments.
        """
        token = self.peek(skip)
        if not token.matches(name):
            raise self.raise_syntax_error(message=error_message)
        return token

    def read(
        self,
        name: TokenNameMatchT,
        error_message: str = "",
        skip: TokenNameMatchT = WHITESPACE_TOKENS,
    ) -> Token:
        """Return the next token and advance to the next token.

        Raise SyntaxError if the token doesn't match.
        """
        result = self.expect(name, error_message=error_message, skip=skip)
        self.next_token = None
        return result

    def try_read(
        self, name: TokenNameMatchT, skip: TokenNameMatchT = WHITESPACE_TOKENS
    ) -> Optional[Token]:
        """read() if the next token matches the given arguments.

        Do nothing if it does not match.
        """
        if self.match(name, skip=skip):
            return self.read(self.rules, skip=skip)
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

    def _make_token(self, name: TokenNameMatchT, text: str) -> Token:
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

                    yield self._make_token(name, token_text)
                    self.position += len(token_text)
                    break
            else:
                raise self.raise_syntax_error(message="Unrecognized token")
        yield self._make_token("END", "")
