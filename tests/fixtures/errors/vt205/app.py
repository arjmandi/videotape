import videotape as vt


class Drink(vt.Record, key="name"):
    name: str
    price: int


drinks = vt.table(Drink, "drinks.json")
app = vt.Screenplay("Cafe")


@app.scene
def home():
    return [vt.Heading("Cafe")]
