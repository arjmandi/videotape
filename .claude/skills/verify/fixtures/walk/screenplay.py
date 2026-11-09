import videotape as vt

play = vt.Screenplay("Walk", look="A plain room.")
play.scene("hall", direction="A long hall.", actions={"Left door": "left", "Right door": "right"})
play.scene("left", direction="A small study.", actions={"Open desk": "desk"})
play.scene("right", direction="A small kitchen.", actions={"Open fridge": "fridge"})
play.scene("desk", direction="An open drawer.")
play.scene("fridge", direction="A lit shelf.")
