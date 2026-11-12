import videotape as vt

app = vt.Screenplay("Counter")


@app.scene
def home():
    return [vt.Button("Start", to=count(1))]


@app.scene
def count(n: int):
    return [vt.Text(f"{n}"), vt.Button("More", to=count(n + 1))]
