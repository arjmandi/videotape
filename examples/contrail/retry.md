# What to redo with more budget

The terminal tape stopped at its $250 cap on 2026-11-21 with failing shots. Each one below is a real failure, seen in
its frames, and the fix it needs is a story line, so redoing it redraws every shot drawn from what it changes. Run
`uv run videotape plan --story terminal` for the estimate before raising the cap.

## Terminal: the gate sign changes in place

Every Heading, Text and Button in `stories/terminal.toml` is drawn on a dark sign, so the model draws `booked` on the
same gate sign as `flight`, and a press changes that sign's words in place, which `VT507` rightly calls a dissolve.
The results board does the same when a row is pressed. Two story lines fix it:

1. `scenes.booked`: the camera looks down at the printed boarding pass on the gate desk, its words printed on it,
   and the sign above out of view. This redraws the booked keys and every move into and out of booked, about 54
   shots, roughly $50.
2. `moves.List`: the row lights up, and the camera turns from the board, which keeps its words, and walks to the
   gate desk. This redraws the flight base, which is rehearsed from a row's press, and so every flight and booked
   key and move after it, about 90 shots, roughly $80.

Then retake whatever still fails, as in `uv run videotape retake "<shot>" --story terminal --takes 2`. The dailies
list each failing shot with its `retake` command.

## Terminal: variants that keep their base's AM

`flight(CT 504, 2026-12-13)`, `flight(CT 306, 2026-12-13)` and `flight(CT 100, 2026-12-11)` are drawn from the
picture of `flight(CT 500, 2026-12-11)`, which leaves at 9:00 AM. Six takes each kept "AM" where the line says "PM",
or the base's miles, though the variant's prompt says only the lettering changes and none of the first picture's
words remain. Retakes alone did not fix them. Try more retakes first; if they still fail, the fix is in how a
variant is drawn (the engine's `RELETTERED` clause in `videotape/story.py`), which redraws every variant of every
scene in both stories.

## Moves left failing after the last retakes

The dailies list them: `uv run videotape dailies --story terminal`. Each is a pinned move, so a retake redraws
nothing else.
