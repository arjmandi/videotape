import videotape as vt

play = vt.Screenplay("Missing scene", look="A plain room.")
play.scene("home", shows=["Home"], direction="A desk.", actions={"Open settings": "settings"})
