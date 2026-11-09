import videotape as vt

shop = vt.Screenplay("Brushstroke Surf Co.", look="A small surf shop on the California coast in warm "
    "afternoon light: whitewashed wood, sea air, and surfboards hand-painted in bright patterns.")
shop.scene("welcome", shows=["Brushstroke Surf Co.", "Hand-painted surfboards from California"],
    direction="The shop's front by the beach, its name painted over the open door.",
    actions={"Enter shop": vt.go("entrance", move="The camera walks through the open door.")})
shop.scene("entrance", shows=["How would you like to come in?"], direction="Just inside, by the counter.",
    actions={"I have an account": "login", "Create an account": "signup", "Browse as guest": "gallery"})
shop.scene("login", shows=["Log in", "Email", "Password"], direction="A card on the counter.")
shop.scene("signup", shows=["Create your account", "Email", "Password"],
    direction="A sign-up card on a stand.", actions={"Sign up": "login"})
shop.scene("gallery", shows=["The gallery"],
    direction="Hand-painted surfboards stand in a long row against a whitewashed wall.")
