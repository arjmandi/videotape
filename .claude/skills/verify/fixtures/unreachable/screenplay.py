import videotape as vt

play = vt.Screenplay("Unreachable", look="A plain room.")
play.scene("home", shows=["Home"], direction="A desk.")
play.scene("attic", shows=["Attic"], direction="Dusty boxes under a slanted roof.")
