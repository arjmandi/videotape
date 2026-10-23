"""secret-shown: a frame shows a record with a secret field."""

import videotape as vt


class Account(vt.Record):
    name: str
    password: vt.Secret


account = vt.tape("account", [vt.frame("See my account", shows=Account, actions=[vt.action("Back", vt.back())])])

app = vt.app("account", entry="account", tapes=[account])
