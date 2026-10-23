"""unsourced-record: the frame shows a Profile, but nothing loads it and its name has no default."""

import videotape as vt


class Profile(vt.Record):
    name: str
    bio: str = ""


home = vt.tape("home", [vt.frame("See my profile", shows=Profile, actions=[vt.action("More", vt.jump("more"))])])
more = vt.tape("more", [vt.frame("Read more")])

app = vt.app("site", entry=home, tapes=[home, more])
