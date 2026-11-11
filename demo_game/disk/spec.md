# Dungeon

A small turn-based dungeon game, written as a Python library (no screen, no input loop). Standard library only.
Put every file directly in the workspace folder. Positions are `[row, col]` lists, row 0 at the top.

A level is a list of equal-length strings:
`#` wall, `.` floor, `@` the player's start, `k` the key, `E` the locked exit, `^` a pit.

## Step 1
Create `level.py` with `load(rows) -> dict` returning `{"height", "width", "walls", "start", "key", "exit", "pits"}`:
`walls` and `pits` are lists of positions, and `start`, `key` and `exit` are positions (`key` is None if there is
none). Raise `ValueError` if there is not exactly one `@`.

## Step 2
Create `game.py` with `new_game(level) -> state` and `step(state, action) -> state`. `level` is a list of strings
as above. The state is a plain dict: `{"level": load(level), "pos": [row, col], "lives": 3, "has_key": False,
"status": "playing"}`. `step` never changes the state it is given; it returns a new dict.
Actions are `"n"`, `"s"`, `"e"` and `"w"`; any other action raises `ValueError`. Walls and the edge of the grid block
a move: the player stays where they are.

## Step 3
Walking onto the key picks it up (`has_key` becomes True). The exit is locked: without the key it blocks like a
wall. Walking onto the exit with the key wins: `status` becomes `"won"`.

## Step 4
Create `hazards.py` with the pit logic and use it in `step`. The pit costs a life.

## Step 5
The player has a budget of 20 moves: the state gets `"moves_left": 20`. Every action uses one move, even a blocked
one. When `moves_left` reaches 0 and the player has not won, `status` becomes `"lost"`.

## Step 6
When `lives` reaches 0, `status` becomes `"lost"`. Once the game is won or lost, `step` returns the state unchanged.

## Step 7
Create `render.py` with `render(state) -> str`: the level's rows joined with `"\n"`, with `@` at the player's
position, `.` where the start was, and `.` where the key was once it has been picked up.
