import sys
import re
import argparse
from typing import List, Tuple, Union, Dict, Any


# ---------- Лексический анализатор ----------
class Token:
    def __init__(self, type: str, value: str, line: int, col: int):
        self.type = type
        self.value = value
        self.line = line
        self.col = int(col)

    def __repr__(self):
        return f"Token({self.type}, '{self.value}', {self.line}:{self.col})"


class Lexer:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens = []

    def tokenize(self) -> List[Token]:
        token_specs = [
            ('NUMBER', r'\d+(\.\d*)?|\.\d+'),
            ('ARRAY_OPEN', r'array\('),
            ('PAREN_CLOSE', r'\)'),  # Общая закрывающая скобка
            ('COMMA', r','),
            ('IS', r'is'),
            ('PIPE_OPEN', r'\|'),
            ('PIPE_CLOSE', r'\|'),
            ('PLUS', r'\+'),
            ('MINUS', r'-'),
            ('MULTIPLY', r'\*'),
            ('SORT', r'sort\('),
            ('NAME', r'[_a-zA-Z][_a-zA-Z0-9]*'),
            ('COMMENT', r'#.*'),
            ('WHITESPACE', r'\s+'),
            ('MISMATCH', r'.'),
        ]

        tok_regex = '|'.join(f'(?P<{name}>{pattern})' for name, pattern in token_specs)

        for mo in re.finditer(tok_regex, self.text):
            kind = mo.lastgroup
            value = mo.group()
            col = mo.start() - self.text.rfind('\n', 0, mo.start()) - 1
            col = max(col, 0) + 1

            if kind == 'WHITESPACE':
                self.line += value.count('\n')
                continue
            elif kind == 'COMMENT':
                self.line += value.count('\n')
                continue
            elif kind == 'MISMATCH':
                raise SyntaxError(f"Неизвестный символ '{value}' на строке {self.line}, позиция {col}")

            # Определяем PIPE_OPEN или PIPE_CLOSE
            if kind == 'PIPE_OPEN' or kind == 'PIPE_CLOSE':
                open_pipes = len([t for t in self.tokens if t.type == 'PIPE_OPEN'])
                close_pipes = len([t for t in self.tokens if t.type == 'PIPE_CLOSE'])
                if open_pipes <= close_pipes:
                    kind = 'PIPE_OPEN'
                else:
                    kind = 'PIPE_CLOSE'

            token = Token(kind, value, self.line, col)
            self.tokens.append(token)

            self.line += value.count('\n')

        return self.tokens


# ---------- Синтаксический анализатор ----------
class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0
        self.constants: Dict[str, Any] = {}
        self.output = {}

    def current_token(self) -> Union[Token, None]:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def eat(self, token_type: str) -> Token:
        token = self.current_token()
        if token and token.type == token_type:
            self.pos += 1
            return token
        if token:
            raise SyntaxError(f"Ожидался {token_type}, получен {token.type} на строке {token.line}:{token.col}")
        else:
            raise SyntaxError(f"Ожидался {token_type}, получен EOF")

    def parse(self) -> Dict[str, Any]:
        while self.current_token():
            if self.current_token().type == 'NAME':
                name_token = self.eat('NAME')
                if self.current_token() and self.current_token().type == 'IS':
                    self.eat('IS')
                    value = self.parse_value()
                    # Первые объявления считаем константами
                    if name_token.value not in self.output:
                        self.constants[name_token.value] = value
                    self.output[name_token.value] = value
                else:
                    raise SyntaxError(f"Ожидалось 'is' после имени на строке {name_token.line}:{name_token.col}")
            else:
                token = self.current_token()
                raise SyntaxError(f"Неожиданный токен {token.type} на строке {token.line}:{token.col}")
        return self.output

    def parse_value(self) -> Any:
        token = self.current_token()
        if not token:
            raise SyntaxError("Ожидалось значение, получен EOF")

        if token.type == 'NUMBER':
            self.eat('NUMBER')
            if '.' in token.value:
                return float(token.value)
            return int(token.value)
        elif token.type == 'ARRAY_OPEN':
            return self.parse_array()
        elif token.type == 'PIPE_OPEN':
            return self.parse_constant_expr()
        elif token.type == 'NAME':
            name = self.eat('NAME').value
            if name in self.constants:
                return self.constants[name]
            elif name in self.output:
                return self.output[name]
            raise NameError(f"Константа '{name}' не определена на строке {token.line}:{token.col}")
        else:
            raise SyntaxError(
                f"Неверное значение: ожидалось число, массив или выражение, получен {token.type} на строке {token.line}:{token.col}")

    def parse_array(self) -> List[Any]:
        self.eat('ARRAY_OPEN')
        arr = []

        if self.current_token() and self.current_token().type == 'PAREN_CLOSE':
            self.eat('PAREN_CLOSE')
            return arr

        arr.append(self.parse_value())

        while self.current_token() and self.current_token().type == 'COMMA':
            self.eat('COMMA')
            arr.append(self.parse_value())

        self.eat('PAREN_CLOSE')
        return arr

    def parse_constant_expr(self) -> Any:
        self.eat('PIPE_OPEN')

        # Смотрим, что идет после |
        token = self.current_token()
        if not token:
            raise SyntaxError("Незавершенное выражение в | |")

        # Если сразу идет sort, это вызов функции
        if token.type == 'SORT':
            return self.parse_sort_function()

        # Иначе парсим выражение
        left = self.parse_value()

        token = self.current_token()
        if not token:
            raise SyntaxError("Незавершенное выражение в | |")

        if token.type == 'PIPE_CLOSE':
            # Просто значение в скобках
            self.eat('PIPE_CLOSE')
            return left

        elif token.type in ('PLUS', 'MINUS', 'MULTIPLY'):
            # Бинарная операция
            op_token = self.eat(token.type)
            right = self.parse_value()
            self.eat('PIPE_CLOSE')

            if op_token.type == 'PLUS':
                return left + right
            elif op_token.type == 'MINUS':
                return left - right
            elif op_token.type == 'MULTIPLY':
                return left * right
        else:
            raise SyntaxError(f"Неизвестный оператор {token.type} в выражении на строке {token.line}:{token.col}")

    def parse_sort_function(self) -> Any:
        """Парсит выражение sort(выражение)"""
        self.eat('SORT')  # eat 'sort('

        # Парсим аргумент функции
        arg = self.parse_value()

        # Закрывающая скобка функции sort()
        self.eat('PAREN_CLOSE')

        # Проверяем, что аргумент - массив
        if not isinstance(arg, list):
            raise TypeError(f"sort() ожидает массив, получен {type(arg).__name__}")

        self.eat('PIPE_CLOSE')
        return sorted(arg)


# ---------- Преобразование в YAML ----------
def dict_to_yaml(data: Dict[str, Any], indent=0) -> str:
    yaml_lines = []
    for key, value in data.items():
        if isinstance(value, dict):
            yaml_lines.append(f"{'  ' * indent}{key}:")
            yaml_lines.append(dict_to_yaml(value, indent + 1))
        elif isinstance(value, list):
            yaml_lines.append(f"{'  ' * indent}{key}:")
            for item in value:
                if isinstance(item, dict):
                    yaml_lines.append(f"{'  ' * (indent + 1)}-")
                    yaml_lines.append(dict_to_yaml(item, indent + 2))
                else:
                    yaml_lines.append(f"{'  ' * (indent + 1)}- {item}")
        else:
            yaml_lines.append(f"{'  ' * indent}{key}: {value}")
    return "\n".join(yaml_lines)


# ---------- Основная программа ----------
def main():
    parser = argparse.ArgumentParser(description="Конвертер учебного конфигурационного языка в YAML")
    parser.add_argument("input_file", help="Путь к входному файлу")
    args = parser.parse_args()

    try:
        with open(args.input_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Ошибка: Файл {args.input_file} не найден", file=sys.stderr)
        sys.exit(1)

    try:
        lexer = Lexer(content)
        tokens = lexer.tokenize()
        parser = Parser(tokens)
        result = parser.parse()
        yaml_output = dict_to_yaml(result)
        print(yaml_output)
    except (SyntaxError, NameError, TypeError) as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
