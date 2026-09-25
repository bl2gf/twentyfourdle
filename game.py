"""Exact 24 arithmetic and a deterministic daily puzzle schedule."""
import ast
import hashlib
import json
from datetime import datetime, timezone
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc).date()
COSTS = {ast.Add: 1, ast.Sub: 1, ast.Mult: 2, ast.Div: 3}


def today():
    return datetime.now(timezone.utc).date().isoformat()


def puzzle(day):
    date = datetime.strptime(day, '%Y-%m-%d').date()
    deck = json.loads(Path(__file__).with_name('puzzles.json').read_text())
    # A fixed permutation visits every puzzle once before the deck repeats.
    deck.sort(key=lambda ns: hashlib.sha256(('twentyfourdle-v1:' + str(ns)).encode()).digest())
    return deck[(date - EPOCH).days % len(deck)]


def evaluate(expression, cards):
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 120:
        raise ValueError('Enter a solution using the four numbers.')
    expression = expression.replace('×', '*').replace('÷', '/').replace('−', '-').strip()
    if any(c not in '0123456789+-*/() \t' for c in expression):
        raise ValueError('Use numbers, +, −, ×, ÷, and parentheses only.')
    try:
        tree = ast.parse(expression, mode='eval')
    except (SyntaxError, RecursionError):
        raise ValueError('Check your expression and parentheses.') from None
    used = []

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) is int and 1 <= node.value <= 9:
            used.append(node.value)
            return Fraction(node.value), 0
        if isinstance(node, ast.BinOp) and type(node.op) in COSTS:
            a, ac = visit(node.left)
            b, bc = visit(node.right)
            if isinstance(node.op, ast.Add): value = a + b
            elif isinstance(node.op, ast.Sub): value = a - b
            elif isinstance(node.op, ast.Mult): value = a * b
            else:
                if b == 0: raise ValueError('Division by zero is not allowed.')
                value = a / b
            return value, ac + bc + COSTS[type(node.op)]
        raise ValueError('Use only +, −, ×, ÷. No powers, factorials, or joined numbers.')

    value, score = visit(tree.body)
    if sorted(used) != sorted(cards):
        raise ValueError('Use each of today’s four numbers exactly once.')
    if value != 24:
        raise ValueError(f'That equals {value}, not 24. Keep going!')
    return {'expression': expression, 'score': score}


@lru_cache(maxsize=512)
def solve(cards):
    """Subset dynamic programming; keeps the cheapest expression for every value."""
    dp = {}
    for i, value in enumerate(cards): dp[1 << i] = {Fraction(value): (0, str(value))}
    for mask in range(1, 1 << len(cards)):
        if mask in dp: continue
        values = {}
        left = (mask - 1) & mask
        while left:
            right = mask ^ left
            if right:
                for a, (ac, ae) in dp[left].items():
                    for b, (bc, be) in dp[right].items():
                        candidates = [(a + b, '+', 1), (a - b, '-', 1), (a * b, '*', 2)]
                        if b: candidates.append((a / b, '/', 3))
                        for result, symbol, cost in candidates:
                            score = ac + bc + cost
                            if result not in values or score < values[result][0]:
                                values[result] = (score, f'({ae} {symbol} {be})')
            left = (left - 1) & mask
        dp[mask] = values
    answer = dp[(1 << len(cards)) - 1].get(Fraction(24))
    return {'score': answer[0], 'expression': answer[1][1:-1]} if answer else None
