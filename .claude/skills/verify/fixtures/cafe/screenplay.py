import videotape as vt

cafe = vt.Screenplay("Tidepool Cafe", look="A tiny seaside cafe at dawn, chalkboards and blue tiles.")
cafe.scene("menu", shows=["Today's menu", "Coffee", "Toast"], direction="A chalkboard menu behind the counter.",
    actions={"Order coffee": "order", "Read reviews": vt.go("reviews", move="The camera pans left to a corkboard.")})
cafe.scene("order", shows=["Your order"], direction="A paper cup on the counter.",
    actions={"Back to menu": "menu"})
cafe.scene("reviews", direction="Handwritten notes pinned to a corkboard.")
