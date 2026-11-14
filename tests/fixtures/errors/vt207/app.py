import videotape as vt


class Drink(vt.Record, key="name"):
    name: str
    price: int


drinks = vt.table(Drink, "data/drinks.json")
app = vt.Screenplay("Cafe")


@app.scene
def home():
    cheap = drinks.where(cost=3)
    return [vt.Heading(f"{cheap.count()} cheap drinks")]
