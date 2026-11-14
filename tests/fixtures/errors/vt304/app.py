import videotape as vt

app = vt.Screenplay("Shop")


@app.scene
def home():
    return [vt.Heading("Shop"), vt.Button("Open", to=detail())]


@app.scene
def detail():
    return [vt.Heading("Detail"), vt.Text("Open daily.")]
