import videotape as vt

play = vt.Screenplay("Clip collision", look="A plain room.")
play.scene("home", shows=["Home"], direction="A desk.", actions={"Sign up": "next", "Sign-up": "next"})
play.scene("next", shows=["Next"], direction="A door.")
