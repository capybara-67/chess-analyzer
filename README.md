# Chess Post-Game Analyzer

This is a fair-play chess analysis tool for completed games. It reads a PGN, replays the match, searches each position with a built-in alpha-beta engine, and reports moves where the player could have chosen a stronger move.

It does not connect to live games, scrape boards, or provide real-time help.

## Quick Start

```bash
python3 analyzer.py sample_game.pgn
```

Analyze your own PGN:

```bash
python3 analyzer.py your_game.pgn --depth 2 --threshold 50
```

Useful options:

```bash
python3 analyzer.py your_game.pgn --side white
python3 analyzer.py your_game.pgn --show-all
python3 analyzer.py your_game.pgn --format json
python3 analyzer.py your_game.pgn --depth 3 --max-plies 30
```

## What The Report Means

Scores are from the player-to-move's perspective.

- `best`: the played move was close to the engine's top choice
- `good`: small loss
- `inaccuracy`: noticeable loss
- `mistake`: serious loss
- `blunder`: large tactical or material loss

Example output line:

```text
- 2. g4 by White: blunder
  Suggested instead: e4 (e2e4)
  Engine score: -mate after played move, +0.30 after suggestion
  Lost value: mate-level swing from White's perspective
```

## Design Notes

- No third-party dependencies.
- Supports normal PGN SAN, castling, promotion, en passant, comments, tags, and simple UCI move tokens.
- Uses legal move generation plus alpha-beta search.
- Default depth is intentionally small so full games finish quickly in pure Python.

## Tests

```sh
python3 -m unittest -v
```

Requires Python 3.10 or newer. Evaluations come from the built-in engine, not Stockfish, and should be treated as approximate. The parser reads a single game per input.
