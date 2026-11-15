"""{{title}}, written as a screenplay. Each function below is a scene, one screen of the app, and the first one is
where the app opens. Calling a scene, as in todo(), names a state for an action to go to."""

import videotape as vt


class Step(vt.Record, key="number"):
    number: int
    title: str
    where: str


steps = vt.table(Step, "data/steps.json")

app = vt.Screenplay("{{title}}")


@app.scene
def home():
    return [
        vt.Heading(app.title),
        vt.Text(f"An app of two scenes. {steps.count()} steps make it yours."),
        vt.Button("See the steps", to=todo()),
    ]


@app.scene
def todo():
    return [
        vt.Heading("Make it yours"),
        vt.List([vt.Row(step.title, step.where) for step in steps.order_by("number")]),
        vt.Button("Back", to=home()),
    ]
