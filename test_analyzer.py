import unittest

from analyzer import Board, Engine, INF, MATE_SCORE, analyze_game, parse_pgn, parse_square


class AnalyzerTests(unittest.TestCase):
    def test_starting_position_has_twenty_legal_moves(self):
        board = Board.starting_position()
        self.assertEqual(len(board.legal_moves()), 20)

    def test_parse_basic_pgn(self):
        game = parse_pgn("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6")
        self.assertEqual([move.san for move in game.moves], ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6"])

    def test_parse_castling(self):
        game = parse_pgn("1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. O-O Nf6")
        self.assertEqual(game.moves[6].san, "O-O")

    def test_en_passant_is_legal(self):
        board = Board.from_fen("8/8/8/3pP3/8/8/8/4K2k w - d6 0 1")
        moves = {move.uci() for move in board.legal_moves()}
        self.assertIn("e5d6", moves)

    def test_fools_mate_blunder_is_detected(self):
        game = parse_pgn("1. f3 e5 2. g4 Qh4#")
        items = analyze_game(game, depth=2)
        g4 = next(item for item in items if item.played_uci == "g2g4")
        self.assertEqual(g4.classification, "blunder")
        self.assertGreater(g4.loss, 200)

    def test_stalemate_is_draw_at_search_horizon(self):
        board = Board.from_fen("k7/8/1QK5/8/8/8/8/8 b - - 0 1")
        self.assertEqual(Engine().search(board, 0, -INF, INF, 0), 0)

    def test_narrow_search_does_not_poison_full_search(self):
        board = Board.from_fen("7k/8/8/8/8/8/6q1/KR6 w - - 0 1")
        engine = Engine()
        engine.search(board, 2, -INF, -10000, 0)
        reused = engine.search(board, 2, -INF, INF, 0)
        fresh = Engine().search(board, 2, -INF, INF, 0)
        self.assertEqual(reused, fresh)

    def test_mate_score_respects_distance_from_root(self):
        board = Board.from_fen("7k/8/5KQ1/8/8/8/8/8 w - - 0 1")
        engine = Engine()
        self.assertEqual(engine.search(board, 2, -INF, INF, 1), MATE_SCORE - 2)
        self.assertEqual(engine.search(board, 2, -INF, INF, 5), MATE_SCORE - 6)

    def test_square_parser(self):
        self.assertEqual(parse_square("a1"), 0)
        self.assertEqual(parse_square("h8"), 63)


if __name__ == "__main__":
    unittest.main()
