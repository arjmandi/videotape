import videotape as vt

app = vt.Screenplay("Bill")


@app.scene
def home():
    return [vt.Button("Split it", to=split(0))]


@app.scene
def split(guests: int):
    return [vt.Text(f"${120 // guests} each")]
