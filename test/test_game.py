import json
import unittest
from pathlib import Path
from game import evaluate, puzzle, solve

class MathTests(unittest.TestCase):
    def test_fractional_solution(self):
        self.assertEqual(evaluate('8 / (3 - 8 / 3)', [3, 3, 8, 8])['score'], 7)

    def test_duplicate_tiles_required(self):
        with self.assertRaisesRegex(ValueError, 'exactly once'):
            evaluate('8 * 3 + 3 - 3', [3, 3, 8, 8])

    def test_unsafe_and_unsupported_syntax(self):
        for expression in ['__import__("os")', '4**2+4+4', '24', '4//4+4+4', '4*(4+4-4)', '4/(4-4)+4', '-4+4+4+4', '4.0+4+4+4']:
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                evaluate(expression, [4,4,4,4])

    def test_display_operators(self):
        self.assertEqual(evaluate('(1 + 2 + 3) × 4',[1,2,3,4])['score'],4)

    def test_optimal_solution(self):
        for cards in [(1,2,3,4),(3,3,8,8),(6,6,6,6),(1,1,1,8)]:
            answer=solve(cards)
            self.assertIsNotNone(answer)
            self.assertEqual(evaluate(answer['expression'],cards)['score'],answer['score'])
        self.assertEqual(solve((6,6,6,6))['score'],3)

    def test_daily_schedule_unique_solvable(self):
        from datetime import date,timedelta
        deck=json.loads(Path('puzzles.json').read_text())
        self.assertEqual(len(deck),len({tuple(c) for c in deck}))
        days=[tuple(puzzle((date(2026,1,1)+timedelta(days=i)).isoformat())) for i in range(len(deck))]
        self.assertEqual(len(days),len(set(days)))
        for cards in days:
            answer=solve(cards)
            self.assertIsNotNone(answer)
            evaluate(answer['expression'],cards)

if __name__=='__main__':unittest.main()
