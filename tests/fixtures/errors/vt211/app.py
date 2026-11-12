import videotape as vt

app = vt.Screenplay("Cafe")


@app.scene
def home():
    return [
        vt.Heading("Café Lumière"),
        vt.Text("We open every single day of the week at seven in the morning sharp."),
    ]
