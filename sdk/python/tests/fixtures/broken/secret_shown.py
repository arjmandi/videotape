"""secret-shown: a frame shows a record with a secret field."""

import videotape as vt


class Account(vt.Record):
    name: str
    password: vt.Secret


account = vt.tape("account", [vt.frame("See my account", shows=Account, actions=[vt.action("More", vt.jump("more"))])])

more = vt.tape("more", [vt.frame("Read more")])

app = vt.app("account", entry="account", tapes=[account, more])
