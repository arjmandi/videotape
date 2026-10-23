"""secret-shown: a frame shows a record with a secret field."""

import videotape as vt


class Account(vt.Record):
    name: str
    password: vt.Secret


async def load_account(ctx) -> Account: ...


account = vt.tape("account", [vt.frame("See my account", shows=Account, enter=load_account, actions=[vt.action("More", vt.jump("more"))])])

more = vt.tape("more", [vt.frame("Read more")])

app = vt.app("account", entry="account", tapes=[account, more])
