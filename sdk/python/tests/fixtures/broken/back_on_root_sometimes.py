"""back-on-root-sometimes: home is the entry (a root), but "more" also jumps back to it with history."""

import videotape as vt


async def leave(ctx):
    return vt.back()


home = vt.tape("home", [vt.frame("Start here", actions=[vt.action("Leave", leave),
                                                         vt.action("More", vt.jump("more"))])])
more = vt.tape("more", [vt.frame("Read more", actions=[vt.action("Home", vt.jump("home"))])])

app = vt.app("site", entry="home", tapes=[home, more])
