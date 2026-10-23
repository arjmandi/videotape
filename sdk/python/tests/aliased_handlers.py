"""Handlers whose module imports videotape under other names."""

import videotape
import videotape as tape_sdk
from videotape import jump as go


async def a(ctx):
    return go("orders", page=2)


async def b(ctx):
    return videotape.stay() if ctx else tape_sdk.back()


def helper():
    return videotape.jump("orders")


async def c(ctx):
    return helper()


@tape_sdk.outcomes(tape_sdk.jump("orders", page=...))
async def d(ctx):
    return helper()


async def e(ctx):
    where = "orders"
    return videotape.jump(where)


async def f(ctx):
    def inner():
        return 1

    inner()
    return videotape.open("https://example.com")
