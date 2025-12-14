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
        self.col = col

    def __repr__(self):
        return f"Token({self.type}, '{self.value}', {self.line}:{self.col})"

class Lexer:
    patterns = [
        (r'array\(', 'ARRAY_OPEN'),
        (r'\)', 'ARRAY_CLOSE'),
        (r',', 'COMMA'),
        (r'is', 'IS'),
        (r'\|', 'PIPE_OPEN'),
        (r'\|', 'PIPE_CLOSE'),
        (r'\+', 'PLUS'),
        (r'-', 'MINUS'),
        (r'\*', 'MULTIPLY'),
        (r'sort\(', 'SORT'),
        (r'\d+\.\d*|\.\d+', 'NUMBER'),
        (r'\d+', 'NUMBER'),
        (r'[_a-zA-Z][_a-zA-Z0-9]*', 'NAME'),
        (r'#.*', 'COMMENT'),
        (r'\s+', 'WHITESPACE'),
    ]

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens = []

    def tokenize(self) -> List[Token]:
        while self.pos < len(self.text):
            matched = False
            for pattern, token_type in self.patterns:
                regex = re.compile(pattern)
                match = regex.match(self.text, self.pos)
                if match:
                    value = match.group(0)
                    start_pos = self.pos
                    self.pos = match.end()
                    if token_type not in ('WHITESPACE', 'COMMENT'):
                        token = Token(token_type, value, self.line, start_pos)
                        self.tokens.append(token)
                    # Обновляем строку и столбец
                    lines = value.count('\n')
                    if lines:
                        self.line += lines
                        self.col = 1 + (self.pos - self.text.rfind('\n', 0, self.pos))
                    else:
                        self.col += len(value)
                    matched = True
                    break
            if not matched:
                raise SyntaxError(f"Неизвестный символ '{self.text[self.pos]}' на позиции {self.pos}")
        return self.tokens

# ---------- Синтаксический анализатор ----------
class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0
        self.constants: Dict[str, Any] = {}
        self.output = {}

    def current_token(self) -> Token:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def eat(self, token_type: str) -> Token:
        token = self.current_token()
        if token and token.type == token_type:
            self.pos += 1
            return token
        raise SyntaxError(f"Ожидался {token_type}, получен {token.type if token else 'EOF'} на строке {token.line if token else '?'}")

    def parse(self) -> Dict[str, Any]:
        while self.current_token():
            if self.current_token().type == 'NAME':
                name_token = self.eat('NAME')
                if self.current_token() and self.current_token().type == 'IS':
                    self.eat('IS')
                    value = self.parse_value()
                    self.constants[name_token.value] = value
                else:
                    # Это ключ для выходного YAML
                    key = name_token.value
                    self.eat('IS')
                    value = self.parse_value()
                    self.output[key] = value
            else:
                raise SyntaxError(f"Неожиданный токен {self.current_token().type}")
        return self.output

    def parse_value(self) -> Any:
        token = self.current_token()
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
            raise NameError(f"Константа '{name}' не определена")
        else:
            raise SyntaxError(f"Неверное значение на токене {token.type}")

    def parse_array(self) -> List[Any]:
        self.eat('ARRAY_OPEN')
        arr = []
        first = True
        while self.current_token() and self.current_token().type != 'ARRAY_CLOSE':
            if not first:
                self.eat('COMMA')
            arr.append(self.parse_value())
            first = False
        self.eat('ARRAY_CLOSE')
        return arr

    def parse_constant_expr(self) -> Any:
        self.eat('PIPE_OPEN')
        # Простое выражение: NAME оператор NAME/NUMBER
        left = self.parse_value()
        token = self.current_token()
        if token.type in ('PLUS', 'MINUS', 'MULTIPLY'):
            op = token.type
            self.eat(token.type)
            right = self.parse_value()
            if op == 'PLUS':
                result = left + right
            elif op == 'MINUS':
                result = left - right
            elif op == 'MULTIPLY':
                result = left * right
        elif token.type == 'SORT':
            self.eat('SORT')
            # sort() применяется к массиву
            if not isinstance(left, list):
                raise TypeError("sort() ожидает массив")
            result = sorted(left)
            self.eat('PIPE_CLOSE')
            return result
        else:
            result = left
        self.eat('PIPE_CLOSE')
        return result

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
    parser.add_argument("input_file.config", help="Путь к входному файлу")
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
