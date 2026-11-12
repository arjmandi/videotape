"""A small app for the tests: a menu of drinks, and each one can be ordered."""

import videotape as vt


class Drink(vt.Record, key="name"):
    name: str
    price: int


drinks = vt.table(Drink, "drinks.json")
app = vt.Screenplay("Corner Cafe")


@app.scene
def menu():
    return [
        vt.Heading("Corner Cafe"),
        vt.List([vt.Row(drink.name, value=f"${drink.price}", to=order(drink)) for drink in drinks.order_by("name")],
                title="Drinks"),
    ]


@app.scene
def order(drink: Drink):
    return [
        vt.Heading(drink.name),
        vt.Text(f"${drink.price}"),
        vt.Button("Order", to=thanks(drink)),
    ]


@app.scene
def thanks(drink: Drink):
    return [vt.Heading("Thanks"), vt.Text(f"One {drink.name} coming up."), vt.Button("Done", to=menu())]
