#!/usr/bin/env python3
"""Dependency-free post-game chess analyzer.

This is intentionally built for completed games only. It reads PGN, replays the
game, searches each position with a small built-in engine, and reports moves
where the engine preferred a different continuation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from typing import Iterable


FILES = "abcdefgh"
RANKS = "12345678"
WHITE = "w"
BLACK = "b"
MATE_SCORE = 100_000
INF = 1_000_000

PIECE_VALUES = {
    "p": 100,
    "n": 320,
    "b": 330,
    "r": 500,
    "q": 900,
    "k": 0,
}

PAWN_TABLE = [
    0, 0, 0, 0, 0, 0, 0, 0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
    5, 5, 10, 25, 25, 10, 5, 5,
    0, 0, 0, 20, 20, 0, 0, 0,
    5, -5, -10, 0, 0, -10, -5, 5,
    5, 10, 10, -20, -20, 10, 10, 5,
    0, 0, 0, 0, 0, 0, 0, 0,
]

KNIGHT_TABLE = [
    -50, -40, -30, -30, -30, -30, -40, -50,
    -40, -20, 0, 5, 5, 0, -20, -40,
    -30, 5, 10, 15, 15, 10, 5, -30,
    -30, 0, 15, 20, 20, 15, 0, -30,
    -30, 5, 15, 20, 20, 15, 5, -30,
    -30, 0, 10, 15, 15, 10, 0, -30,
    -40, -20, 0, 0, 0, 0, -20, -40,
    -50, -40, -30, -30, -30, -30, -40, -50,
]

BISHOP_TABLE = [
    -20, -10, -10, -10, -10, -10, -10, -20,
    -10, 5, 0, 0, 0, 0, 5, -10,
    -10, 10, 10, 10, 10, 10, 10, -10,
    -10, 0, 10, 10, 10, 10, 0, -10,
    -10, 5, 5, 10, 10, 5, 5, -10,
    -10, 0, 5, 10, 10, 5, 0, -10,
    -10, 0, 0, 0, 0, 0, 0, -10,
    -20, -10, -10, -10, -10, -10, -10, -20,
]

ROOK_TABLE = [
    0, 0, 0, 5, 5, 0, 0, 0,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    5, 10, 10, 10, 10, 10, 10, 5,
    0, 0, 0, 0, 0, 0, 0, 0,
]

QUEEN_TABLE = [
    -20, -10, -10, -5, -5, -10, -10, -20,
    -10, 0, 5, 0, 0, 0, 0, -10,
    -10, 5, 5, 5, 5, 5, 0, -10,
    0, 0, 5, 5, 5, 5, 0, -5,
    -5, 0, 5, 5, 5, 5, 0, -5,
    -10, 0, 5, 5, 5, 5, 0, -10,
    -10, 0, 0, 0, 0, 0, 0, -10,
    -20, -10, -10, -5, -5, -10, -10, -20,
]

KING_TABLE = [
    20, 30, 10, 0, 0, 10, 30, 20,
    20, 20, 0, 0, 0, 0, 20, 20,
    -10, -20, -20, -20, -20, -20, -20, -10,
    -20, -30, -30, -40, -40, -30, -30, -20,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
]

PIECE_SQUARE_TABLES = {
    "p": PAWN_TABLE,
    "n": KNIGHT_TABLE,
    "b": BISHOP_TABLE,
    "r": ROOK_TABLE,
    "q": QUEEN_TABLE,
    "k": KING_TABLE,
}


def opponent(color: str) -> str:
    return BLACK if color == WHITE else WHITE


def piece_color(piece: str | None) -> str | None:
    if piece is None:
        return None
    return WHITE if piece.isupper() else BLACK


def square_name(square: int) -> str:
    return FILES[square % 8] + RANKS[square // 8]


def parse_square(name: str) -> int:
    if len(name) != 2 or name[0] not in FILES or name[1] not in RANKS:
        raise ValueError(f"Invalid square: {name}")
    return FILES.index(name[0]) + 8 * RANKS.index(name[1])


def mirror_square(square: int) -> int:
    file_index = square % 8
    rank_index = square // 8
    return file_index + 8 * (7 - rank_index)


@dataclass(frozen=True)
class Move:
    from_sq: int
    to_sq: int
    promotion: str | None = None
    is_en_passant: bool = False
    is_castle: bool = False

    def uci(self) -> str:
        suffix = self.promotion or ""
        return f"{square_name(self.from_sq)}{square_name(self.to_sq)}{suffix}"


@dataclass
class GameMove:
    move: Move
    san: str
    original: str


@dataclass
class ParsedGame:
    tags: dict[str, str]
    starting_fen: str | None
    moves: list[GameMove]


@dataclass
class AnalysisItem:
    ply: int
    move_number: int
    side: str
    played_san: str
    played_uci: str
    best_san: str
    best_uci: str
    played_score: int
    best_score: int
    loss: int
    classification: str

    def to_json(self) -> dict[str, object]:
        return {
            "ply": self.ply,
            "move_number": self.move_number,
            "side": "White" if self.side == WHITE else "Black",
            "played": {"san": self.played_san, "uci": self.played_uci},
            "best": {"san": self.best_san, "uci": self.best_uci},
            "played_score_cp": self.played_score,
            "best_score_cp": self.best_score,
            "loss_cp": self.loss,
            "classification": self.classification,
        }


class Board:
    def __init__(
        self,
        board: list[str | None],
        turn: str = WHITE,
        castling: str = "KQkq",
        ep_square: int | None = None,
        halfmove_clock: int = 0,
        fullmove_number: int = 1,
    ) -> None:
        self.board = board
        self.turn = turn
        self.castling = castling if castling else "-"
        self.ep_square = ep_square
        self.halfmove_clock = halfmove_clock
        self.fullmove_number = fullmove_number

    @classmethod
    def starting_position(cls) -> Board:
        return cls.from_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")

    @classmethod
    def from_fen(cls, fen: str) -> Board:
        parts = fen.strip().split()
        if len(parts) < 4:
            raise ValueError("FEN must contain at least board, turn, castling, and en-passant fields")

        board: list[str | None] = [None] * 64
        ranks = parts[0].split("/")
        if len(ranks) != 8:
            raise ValueError("FEN board field must contain 8 ranks")

        for fen_rank_index, rank_text in enumerate(ranks):
            rank = 7 - fen_rank_index
            file_index = 0
            for char in rank_text:
                if char.isdigit():
                    file_index += int(char)
                elif char in "pnbrqkPNBRQK":
                    if file_index >= 8:
                        raise ValueError("FEN rank has too many files")
                    board[rank * 8 + file_index] = char
                    file_index += 1
                else:
                    raise ValueError(f"Invalid FEN piece: {char}")
            if file_index != 8:
                raise ValueError("FEN rank does not contain exactly 8 files")

        ep_square = None if parts[3] == "-" else parse_square(parts[3])
        halfmove = int(parts[4]) if len(parts) > 4 else 0
        fullmove = int(parts[5]) if len(parts) > 5 else 1
        return cls(board, parts[1], parts[2], ep_square, halfmove, fullmove)

    def copy(self) -> Board:
        return Board(
            self.board.copy(),
            self.turn,
            self.castling,
            self.ep_square,
            self.halfmove_clock,
            self.fullmove_number,
        )

    def fen_key(self) -> tuple[tuple[str | None, ...], str, str, int | None]:
        return (tuple(self.board), self.turn, self.castling, self.ep_square)

    def piece_at(self, square: int) -> str | None:
        return self.board[square]

    def king_square(self, color: str) -> int:
        king = "K" if color == WHITE else "k"
        try:
            return self.board.index(king)
        except ValueError as exc:
            raise ValueError(f"Board is missing {'white' if color == WHITE else 'black'} king") from exc

    def in_check(self, color: str) -> bool:
        return self.is_square_attacked(self.king_square(color), opponent(color))

    def is_square_attacked(self, square: int, by_color: str) -> bool:
        rank = square // 8
        file_index = square % 8

        pawn_rank = rank - 1 if by_color == WHITE else rank + 1
        pawn_piece = "P" if by_color == WHITE else "p"
        if 0 <= pawn_rank < 8:
            for pawn_file in (file_index - 1, file_index + 1):
                if 0 <= pawn_file < 8 and self.board[pawn_rank * 8 + pawn_file] == pawn_piece:
                    return True

        knight_piece = "N" if by_color == WHITE else "n"
        for dr, df in ((2, 1), (2, -1), (-2, 1), (-2, -1), (1, 2), (1, -2), (-1, 2), (-1, -2)):
            r, f = rank + dr, file_index + df
            if 0 <= r < 8 and 0 <= f < 8 and self.board[r * 8 + f] == knight_piece:
                return True

        king_piece = "K" if by_color == WHITE else "k"
        for dr in (-1, 0, 1):
            for df in (-1, 0, 1):
                if dr == 0 and df == 0:
                    continue
                r, f = rank + dr, file_index + df
                if 0 <= r < 8 and 0 <= f < 8 and self.board[r * 8 + f] == king_piece:
                    return True

        diagonal_attackers = {"B", "Q"} if by_color == WHITE else {"b", "q"}
        orthogonal_attackers = {"R", "Q"} if by_color == WHITE else {"r", "q"}
        for dr, df in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            if self._ray_attacked(rank, file_index, dr, df, diagonal_attackers):
                return True
        for dr, df in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if self._ray_attacked(rank, file_index, dr, df, orthogonal_attackers):
                return True
        return False

    def _ray_attacked(self, rank: int, file_index: int, dr: int, df: int, attackers: set[str]) -> bool:
        r, f = rank + dr, file_index + df
        while 0 <= r < 8 and 0 <= f < 8:
            piece = self.board[r * 8 + f]
            if piece is not None:
                return piece in attackers
            r += dr
            f += df
        return False

    def legal_moves(self) -> list[Move]:
        side = self.turn
        moves = []
        for move in self.pseudo_legal_moves():
            child = self.copy()
            child.push(move)
            if not child.in_check(side):
                moves.append(move)
        return moves

    def has_legal_moves(self) -> bool:
        return bool(self.legal_moves())

    def pseudo_legal_moves(self) -> Iterable[Move]:
        for square, piece in enumerate(self.board):
            if piece is None or piece_color(piece) != self.turn:
                continue

            kind = piece.lower()
            if kind == "p":
                yield from self._pawn_moves(square, piece)
            elif kind == "n":
                yield from self._jump_moves(square, ((2, 1), (2, -1), (-2, 1), (-2, -1), (1, 2), (1, -2), (-1, 2), (-1, -2)))
            elif kind == "b":
                yield from self._slide_moves(square, ((1, 1), (1, -1), (-1, 1), (-1, -1)))
            elif kind == "r":
                yield from self._slide_moves(square, ((1, 0), (-1, 0), (0, 1), (0, -1)))
            elif kind == "q":
                yield from self._slide_moves(square, ((1, 1), (1, -1), (-1, 1), (-1, -1), (1, 0), (-1, 0), (0, 1), (0, -1)))
            elif kind == "k":
                yield from self._king_moves(square, piece)

    def _pawn_moves(self, square: int, piece: str) -> Iterable[Move]:
        color = piece_color(piece)
        assert color is not None
        direction = 8 if color == WHITE else -8
        rank = square // 8
        file_index = square % 8
        start_rank = 1 if color == WHITE else 6
        promotion_rank = 7 if color == WHITE else 0

        one_step = square + direction
        if 0 <= one_step < 64 and self.board[one_step] is None:
            if one_step // 8 == promotion_rank:
                for promotion in "qrbn":
                    yield Move(square, one_step, promotion=promotion)
            else:
                yield Move(square, one_step)

            two_step = square + 2 * direction
            if rank == start_rank and self.board[two_step] is None:
                yield Move(square, two_step)

        for df in (-1, 1):
            target_file = file_index + df
            if not 0 <= target_file < 8:
                continue
            target = square + direction + df
            if not 0 <= target < 64:
                continue
            target_piece = self.board[target]
            if target_piece is not None and piece_color(target_piece) == opponent(color):
                if target // 8 == promotion_rank:
                    for promotion in "qrbn":
                        yield Move(square, target, promotion=promotion)
                else:
                    yield Move(square, target)
            elif target == self.ep_square:
                yield Move(square, target, is_en_passant=True)

    def _jump_moves(self, square: int, deltas: Iterable[tuple[int, int]]) -> Iterable[Move]:
        rank = square // 8
        file_index = square % 8
        for dr, df in deltas:
            r, f = rank + dr, file_index + df
            if not (0 <= r < 8 and 0 <= f < 8):
                continue
            target = r * 8 + f
            target_piece = self.board[target]
            if target_piece is None or piece_color(target_piece) != self.turn:
                yield Move(square, target)

    def _slide_moves(self, square: int, deltas: Iterable[tuple[int, int]]) -> Iterable[Move]:
        rank = square // 8
        file_index = square % 8
        for dr, df in deltas:
            r, f = rank + dr, file_index + df
            while 0 <= r < 8 and 0 <= f < 8:
                target = r * 8 + f
                target_piece = self.board[target]
                if target_piece is None:
                    yield Move(square, target)
                else:
                    if piece_color(target_piece) != self.turn:
                        yield Move(square, target)
                    break
                r += dr
                f += df

    def _king_moves(self, square: int, piece: str) -> Iterable[Move]:
        yield from self._jump_moves(square, ((1, 1), (1, 0), (1, -1), (0, 1), (0, -1), (-1, 1), (-1, 0), (-1, -1)))
        color = piece_color(piece)
        assert color is not None

        if color == WHITE and square == parse_square("e1"):
            if "K" in self.castling and self._can_castle_kingside(WHITE):
                yield Move(square, parse_square("g1"), is_castle=True)
            if "Q" in self.castling and self._can_castle_queenside(WHITE):
                yield Move(square, parse_square("c1"), is_castle=True)
        elif color == BLACK and square == parse_square("e8"):
            if "k" in self.castling and self._can_castle_kingside(BLACK):
                yield Move(square, parse_square("g8"), is_castle=True)
            if "q" in self.castling and self._can_castle_queenside(BLACK):
                yield Move(square, parse_square("c8"), is_castle=True)

    def _can_castle_kingside(self, color: str) -> bool:
        if self.in_check(color):
            return False
        if color == WHITE:
            rook_square, f_square, g_square = parse_square("h1"), parse_square("f1"), parse_square("g1")
            rook = "R"
        else:
            rook_square, f_square, g_square = parse_square("h8"), parse_square("f8"), parse_square("g8")
            rook = "r"
        enemy = opponent(color)
        return (
            self.board[rook_square] == rook
            and self.board[f_square] is None
            and self.board[g_square] is None
            and not self.is_square_attacked(f_square, enemy)
            and not self.is_square_attacked(g_square, enemy)
        )

    def _can_castle_queenside(self, color: str) -> bool:
        if self.in_check(color):
            return False
        if color == WHITE:
            rook_square, b_square, c_square, d_square = parse_square("a1"), parse_square("b1"), parse_square("c1"), parse_square("d1")
            rook = "R"
        else:
            rook_square, b_square, c_square, d_square = parse_square("a8"), parse_square("b8"), parse_square("c8"), parse_square("d8")
            rook = "r"
        enemy = opponent(color)
        return (
            self.board[rook_square] == rook
            and self.board[b_square] is None
            and self.board[c_square] is None
            and self.board[d_square] is None
            and not self.is_square_attacked(d_square, enemy)
            and not self.is_square_attacked(c_square, enemy)
        )

    def push(self, move: Move) -> None:
        piece = self.board[move.from_sq]
        if piece is None:
            raise ValueError(f"No piece on {square_name(move.from_sq)}")
        color = piece_color(piece)
        assert color is not None

        captured_piece = self.board[move.to_sq]
        if move.is_en_passant:
            capture_square = move.to_sq - 8 if color == WHITE else move.to_sq + 8
            captured_piece = self.board[capture_square]
            self.board[capture_square] = None

        self.board[move.from_sq] = None

        if move.is_castle:
            self.board[move.to_sq] = piece
            if move.to_sq > move.from_sq:
                rook_from = parse_square("h1") if color == WHITE else parse_square("h8")
                rook_to = parse_square("f1") if color == WHITE else parse_square("f8")
            else:
                rook_from = parse_square("a1") if color == WHITE else parse_square("a8")
                rook_to = parse_square("d1") if color == WHITE else parse_square("d8")
            self.board[rook_to] = self.board[rook_from]
            self.board[rook_from] = None
        else:
            placed_piece = piece
            if piece.lower() == "p" and move.promotion:
                placed_piece = move.promotion.upper() if color == WHITE else move.promotion.lower()
            self.board[move.to_sq] = placed_piece

        rights = set("" if self.castling == "-" else self.castling)
        if piece == "K":
            rights.discard("K")
            rights.discard("Q")
        elif piece == "k":
            rights.discard("k")
            rights.discard("q")

        starting_rook_rights = {
            parse_square("a1"): "Q",
            parse_square("h1"): "K",
            parse_square("a8"): "q",
            parse_square("h8"): "k",
        }
        if move.from_sq in starting_rook_rights:
            rights.discard(starting_rook_rights[move.from_sq])
        if move.to_sq in starting_rook_rights and captured_piece is not None:
            rights.discard(starting_rook_rights[move.to_sq])
        self.castling = "".join(c for c in "KQkq" if c in rights) or "-"

        if piece.lower() == "p" or captured_piece is not None:
            self.halfmove_clock = 0
        else:
            self.halfmove_clock += 1

        if piece.lower() == "p" and abs(move.to_sq - move.from_sq) == 16:
            self.ep_square = (move.from_sq + move.to_sq) // 2
        else:
            self.ep_square = None

        if self.turn == BLACK:
            self.fullmove_number += 1
        self.turn = opponent(self.turn)

    def san(self, move: Move) -> str:
        piece = self.board[move.from_sq]
        if piece is None:
            raise ValueError("Cannot create SAN for a move with no source piece")

        if move.is_castle:
            san = "O-O" if move.to_sq > move.from_sq else "O-O-O"
        else:
            kind = piece.lower()
            target_piece = self.board[move.to_sq]
            is_capture = target_piece is not None or move.is_en_passant

            if kind == "p":
                san = ""
                if is_capture:
                    san += FILES[move.from_sq % 8] + "x"
                san += square_name(move.to_sq)
            else:
                san = kind.upper()
                san += self._disambiguation(move, piece)
                if is_capture:
                    san += "x"
                san += square_name(move.to_sq)

            if move.promotion:
                san += "=" + move.promotion.upper()

        child = self.copy()
        child.push(move)
        if child.in_check(child.turn):
            san += "#" if not child.has_legal_moves() else "+"
        return san

    def _disambiguation(self, move: Move, piece: str) -> str:
        conflicts = [
            other
            for other in self.legal_moves()
            if other != move
            and other.to_sq == move.to_sq
            and self.board[other.from_sq] == piece
        ]
        if not conflicts:
            return ""
        same_file = any(other.from_sq % 8 == move.from_sq % 8 for other in conflicts)
        same_rank = any(other.from_sq // 8 == move.from_sq // 8 for other in conflicts)
        if not same_file:
            return FILES[move.from_sq % 8]
        if not same_rank:
            return RANKS[move.from_sq // 8]
        return square_name(move.from_sq)


class Engine:
    def __init__(self) -> None:
        self.table: dict[tuple[tuple[str | None, ...], str, str, int | None, int], int] = {}

    def root_scores(self, board: Board, depth: int) -> list[tuple[Move, int]]:
        moves = board.legal_moves()
        ordered = sorted(moves, key=lambda move: self._move_order_score(board, move), reverse=True)
        scores = []
        for move in ordered:
            child = board.copy()
            child.push(move)
            score = -self.search(child, max(0, depth - 1), -INF, INF, 1)
            scores.append((move, score))
        return sorted(scores, key=lambda item: item[1], reverse=True)

    def search(self, board: Board, depth: int, alpha: int, beta: int, ply: int) -> int:
        if depth == 0:
            if board.in_check(board.turn) and not board.has_legal_moves():
                return -MATE_SCORE + ply
            return self.static_eval(board)

        key = (*board.fen_key(), depth)
        if key in self.table:
            return self.table[key]

        moves = board.legal_moves()
        if not moves:
            if board.in_check(board.turn):
                return -MATE_SCORE + ply
            return 0

        value = -INF
        ordered = sorted(moves, key=lambda move: self._move_order_score(board, move), reverse=True)
        for move in ordered:
            child = board.copy()
            child.push(move)
            score = -self.search(child, depth - 1, -beta, -alpha, ply + 1)
            value = max(value, score)
            alpha = max(alpha, score)
            if alpha >= beta:
                break

        self.table[key] = value
        return value

    def static_eval(self, board: Board) -> int:
        score = 0
        for square, piece in enumerate(board.board):
            if piece is None:
                continue
            kind = piece.lower()
            base = PIECE_VALUES[kind]
            table = PIECE_SQUARE_TABLES[kind]
            positional = table[square] if piece.isupper() else table[mirror_square(square)]
            value = base + positional
            score += value if piece.isupper() else -value

        # A small tempo bonus keeps the engine from undervaluing initiative.
        score += 10 if board.turn == WHITE else -10
        return score if board.turn == WHITE else -score

    def _move_order_score(self, board: Board, move: Move) -> int:
        piece = board.piece_at(move.from_sq)
        captured = board.piece_at(move.to_sq)
        score = 0
        if captured is not None and piece is not None:
            score += 10 * PIECE_VALUES[captured.lower()] - PIECE_VALUES[piece.lower()]
        if move.is_en_passant:
            score += 1000
        if move.promotion:
            score += PIECE_VALUES[move.promotion]
        if move.is_castle:
            score += 20
        return score


def strip_pgn_comments_and_variations(text: str) -> str:
    text = re.sub(r";[^\n]*", " ", text)
    text = re.sub(r"\{[^}]*\}", " ", text, flags=re.DOTALL)
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"\([^()]*\)", " ", text, flags=re.DOTALL)
    return text


def parse_tags(text: str) -> tuple[dict[str, str], str]:
    tags: dict[str, str] = {}
    body_lines = []
    tag_re = re.compile(r'^\s*\[([A-Za-z0-9_]+)\s+"(.*)"\]\s*$')
    for line in text.splitlines():
        match = tag_re.match(line)
        if match:
            tags[match.group(1)] = match.group(2)
        else:
            body_lines.append(line)
    return tags, "\n".join(body_lines)


def pgn_tokens(body: str) -> list[str]:
    cleaned = strip_pgn_comments_and_variations(body)
    raw_tokens = cleaned.replace("\n", " ").split()
    tokens: list[str] = []

    for token in raw_tokens:
        token = token.strip()
        if not token:
            continue
        if token in {"1-0", "0-1", "1/2-1/2", "*"} or token.startswith("$"):
            continue

        while True:
            match = re.match(r"^\d+\.(?:\.\.)?(.*)$", token)
            if not match:
                break
            token = match.group(1)
            if not token:
                break
        if not token:
            continue
        if token in {"...", "."}:
            continue
        tokens.append(token)

    return tokens


def normalize_san(token: str) -> str:
    token = token.strip()
    token = token.replace("0", "O")
    token = token.replace(" e.p.", "").replace("e.p.", "")
    token = re.sub(r"[!?]+$", "", token)
    token = token.rstrip("+#")
    token = token.replace("=Q", "=Q").replace("=R", "=R").replace("=B", "=B").replace("=N", "=N")
    return token


def parse_move_token(board: Board, token: str) -> Move:
    clean = normalize_san(token)
    legal_moves = board.legal_moves()

    token_uci = clean.lower()
    for move in legal_moves:
        if token_uci == move.uci():
            return move
        if len(token_uci) == 4 and move.promotion is None and token_uci == move.uci():
            return move

    for move in legal_moves:
        if normalize_san(board.san(move)) == clean:
            return move

    # Be forgiving with promotion notation like e8Q instead of e8=Q.
    if len(clean) >= 3 and clean[-1] in "QRBN" and "=" not in clean:
        promoted = clean[:-1] + "=" + clean[-1]
        for move in legal_moves:
            if normalize_san(board.san(move)) == promoted:
                return move

    examples = ", ".join(board.san(move) for move in legal_moves[:12])
    raise ValueError(f"Could not parse move token '{token}' at move {board.fullmove_number}. Legal examples: {examples}")


def parse_pgn(text: str) -> ParsedGame:
    tags, body = parse_tags(text)
    starting_fen = tags.get("FEN")
    board = Board.from_fen(starting_fen) if starting_fen else Board.starting_position()
    moves: list[GameMove] = []

    for token in pgn_tokens(body):
        move = parse_move_token(board, token)
        san = board.san(move)
        moves.append(GameMove(move=move, san=san, original=token))
        board.push(move)

    return ParsedGame(tags=tags, starting_fen=starting_fen, moves=moves)


def classify_loss(loss: int) -> str:
    if loss < 20:
        return "best"
    if loss < 50:
        return "good"
    if loss < 100:
        return "inaccuracy"
    if loss < 200:
        return "mistake"
    return "blunder"


def analyze_game(game: ParsedGame, depth: int = 2, max_plies: int | None = None) -> list[AnalysisItem]:
    board = Board.from_fen(game.starting_fen) if game.starting_fen else Board.starting_position()
    engine = Engine()
    items: list[AnalysisItem] = []

    for ply_index, game_move in enumerate(game.moves, start=1):
        if max_plies is not None and ply_index > max_plies:
            break

        move_number = board.fullmove_number
        side = board.turn
        played_san = board.san(game_move.move)
        scores = engine.root_scores(board, depth)
        if not scores:
            break
        best_move, best_score = scores[0]
        score_by_uci = {move.uci(): score for move, score in scores}
        played_score = score_by_uci.get(game_move.move.uci())
        if played_score is None:
            child = board.copy()
            child.push(game_move.move)
            played_score = -engine.search(child, max(0, depth - 1), -INF, INF, 1)

        loss = max(0, best_score - played_score)
        items.append(
            AnalysisItem(
                ply=ply_index,
                move_number=move_number,
                side=side,
                played_san=played_san,
                played_uci=game_move.move.uci(),
                best_san=board.san(best_move),
                best_uci=best_move.uci(),
                played_score=played_score,
                best_score=best_score,
                loss=loss,
                classification=classify_loss(loss),
            )
        )
        board.push(game_move.move)

    return items


def cp_to_text(score: int) -> str:
    if score > MATE_SCORE - 1000:
        return "+mate"
    if score < -MATE_SCORE + 1000:
        return "-mate"
    return f"{score / 100:+.2f}"


def loss_to_text(loss: int) -> str:
    if loss > MATE_SCORE - 1000:
        return "mate-level swing"
    return f"{loss / 100:.2f} pawns"


def move_label(item: AnalysisItem) -> str:
    suffix = "." if item.side == WHITE else "..."
    return f"{item.move_number}{suffix}"


def side_name(side: str) -> str:
    return "White" if side == WHITE else "Black"


def render_text_report(
    game: ParsedGame,
    items: list[AnalysisItem],
    threshold: int,
    top: int,
    side_filter: str,
    show_all: bool,
    depth: int,
) -> str:
    tags = game.tags
    white = tags.get("White", "White")
    black = tags.get("Black", "Black")
    event = tags.get("Event", "PGN game")

    counts = {"best": 0, "good": 0, "inaccuracy": 0, "mistake": 0, "blunder": 0}
    for item in items:
        counts[item.classification] += 1

    allowed_side = {WHITE, BLACK}
    if side_filter == "white":
        allowed_side = {WHITE}
    elif side_filter == "black":
        allowed_side = {BLACK}

    filtered = [item for item in items if item.side in allowed_side]
    if not show_all:
        filtered = [item for item in filtered if item.loss >= threshold]
    filtered = filtered[:top]

    lines = [
        "Post-game chess analysis",
        f"Game: {white} vs {black} ({event})",
        f"Engine: built-in alpha-beta search, depth {depth}",
        f"Analyzed plies: {len(items)}",
        "",
        "Summary:",
        f"  Best/good: {counts['best'] + counts['good']}",
        f"  Inaccuracies: {counts['inaccuracy']}",
        f"  Mistakes: {counts['mistake']}",
        f"  Blunders: {counts['blunder']}",
        "",
    ]

    if not filtered:
        lines.append(f"No moves crossed the {threshold} cp reporting threshold.")
        return "\n".join(lines)

    lines.append("Recommendations:")
    for item in filtered:
        loss_text = loss_to_text(item.loss)
        lines.extend(
            [
                f"- {move_label(item)} {item.played_san} by {side_name(item.side)}: {item.classification}",
                f"  Suggested instead: {item.best_san} ({item.best_uci})",
                f"  Engine score: {cp_to_text(item.played_score)} after played move, {cp_to_text(item.best_score)} after suggestion",
                f"  Lost value: {loss_text} from {side_name(item.side)}'s perspective",
            ]
        )
    return "\n".join(lines)


def render_json_report(game: ParsedGame, items: list[AnalysisItem], depth: int) -> str:
    return json.dumps(
        {
            "tags": game.tags,
            "starting_fen": game.starting_fen,
            "engine": {"name": "built-in-alpha-beta", "depth": depth},
            "moves": [item.to_json() for item in items],
        },
        indent=2,
    )


def read_pgn(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as file:
        return file.read()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze a completed chess PGN and suggest stronger moves.",
    )
    parser.add_argument("pgn", help="Path to a PGN file, or '-' to read PGN from stdin")
    parser.add_argument("--depth", type=int, default=2, help="Search depth in plies. Default: 2")
    parser.add_argument("--threshold", type=int, default=50, help="Minimum centipawn loss to report. Default: 50")
    parser.add_argument("--top", type=int, default=20, help="Maximum report items. Default: 20")
    parser.add_argument("--side", choices=["both", "white", "black"], default="both", help="Only report one side")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Report format")
    parser.add_argument("--show-all", action="store_true", help="Show every analyzed move instead of thresholded issues")
    parser.add_argument("--max-plies", type=int, default=None, help="Stop after this many half-moves")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.depth < 1:
        parser.error("--depth must be at least 1")
    if args.top < 1:
        parser.error("--top must be at least 1")
    if args.max_plies is not None and args.max_plies < 1:
        parser.error("--max-plies must be at least 1")
    if args.threshold < 0:
        parser.error("--threshold must be non-negative")

    try:
        game = parse_pgn(read_pgn(args.pgn))
        items = analyze_game(game, depth=args.depth, max_plies=args.max_plies)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(render_json_report(game, items, args.depth))
    else:
        print(render_text_report(game, items, args.threshold, args.top, args.side, args.show_all, args.depth))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
