import videotape as vt

app = vt.Screenplay("Shop")


@app.scene
def home():
    return [vt.Heading("Shop")]


@app.scene
def help():
    return [vt.Text("Call us.")]
