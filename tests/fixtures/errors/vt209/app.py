import videotape as vt

app = vt.Screenplay("Mail")


@app.scene
def home():
    return [vt.Button("Open", to=inbox()), vt.Button("Open", to=archive())]


@app.scene
def inbox():
    return [vt.Heading("Inbox")]


@app.scene
def archive():
    return [vt.Heading("Archive")]
