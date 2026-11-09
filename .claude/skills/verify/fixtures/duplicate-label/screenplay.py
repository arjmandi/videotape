import videotape as vt

play = vt.Screenplay("Duplicate label", look="A plain room.")
play.scene("home", shows=["Home"], direction="A desk.",
    actions={"Continue": "next", "Continue": "home"})
play.scene("next", shows=["Next"], direction="A door.")
