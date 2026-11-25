"""Validate the bounded arithmetic grammar used by the dashboard interpreter."""
import json
import math
import re

TOKEN = re.compile(r'\s+|(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|"(?:[^"\\\n\r]|\\["\\/bfnrt]|\\u[\da-fA-F]{4})*"|[A-Za-z_][A-Za-z_0-9]*|[()+\-*/%,]')


def validate_formula(value):
    if not value:
        return value
    raw = TOKEN.findall(value)
    tokens = [token for token in raw if token.strip()]
    if len(value) > 512 or ''.join(raw) != value or len(tokens) > 128:
        raise ValueError('invalid_formula')
    position = 0

    def take(expected=None):
        nonlocal position
        if position >= len(tokens):
            raise ValueError('invalid_formula')
        token = tokens[position]; position += 1
        if expected is not None and token != expected:
            raise ValueError('invalid_formula')
        return token

    def atom(depth):
        if depth > 16:
            raise ValueError('invalid_formula')
        token = take()
        if token in ('+', '-'):
            return [atom(depth + 1)]
        if token == '(':
            node = expression(0, depth + 1); take(')'); return node
        if token == 'value':
            return []
        if token[0].isdigit() or token.startswith('.'):
            if not math.isfinite(float(token)):
                raise ValueError('invalid_formula')
            return []
        if token not in ('field', 'abs', 'round', 'floor', 'ceil', 'min', 'max'):
            raise ValueError('invalid_formula')
        take('(')
        if token == 'field':
            raw_path = take()
            if not raw_path.startswith('"'):
                raise ValueError('invalid_formula')
            path = json.loads(raw_path)
            normalized = re.sub(r'\[(\d+)\]', r'.\1', re.sub(r'^\$\.?', '', path))
            if len(path) > 200 or not re.fullmatch(r'[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)*', normalized) or any(key in ('__proto__', 'constructor', 'prototype') for key in normalized.split('.')):
                raise ValueError('invalid_formula')
            take(')'); return []
        args = [expression(0, depth + 1)]
        while position < len(tokens) and tokens[position] == ',':
            take(','); args.append(expression(0, depth + 1))
        take(')')
        if len(args) > (8 if token in ('min', 'max') else 2 if token == 'round' else 1):
            raise ValueError('invalid_formula')
        return args

    def expression(priority, depth):
        left = atom(depth)
        priorities = {'+': 1, '-': 1, '*': 2, '/': 2, '%': 2}
        while position < len(tokens) and priorities.get(tokens[position], 0) > priority:
            op = take()
            left = [left, expression(priorities[op], depth + 1)]
        return left

    def check_depth(node, depth=0):
        if depth > 16:
            raise ValueError('invalid_formula')
        for child in node:
            check_depth(child, depth + 1)

    check_depth(expression(0, 0))
    if position != len(tokens):
        raise ValueError('invalid_formula')
    return value
