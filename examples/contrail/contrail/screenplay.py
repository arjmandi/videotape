"""Contrail books one-way flights from San Francisco. Each function below is a scene, one screen of
the app, and the first one is where the app opens. Calling a scene, as in results(place, day), names
a state for an action to go to. A search bar with options lists them, and typing a city or an airport
code narrows the list to the ones that match; no_match is where text that matches none goes."""

from datetime import date
from itertools import accumulate

import videotape as vt

from contrail.copy import clock, confirmation, duration, joined, long_day, money, short_day, stops, times
from contrail.data import Airport, Flight, Trip, airports, flights, traveler, trips

TODAY = date(2026, 12, 1)
SHOWN = {6: "Jun", 7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov"}

app = vt.Screenplay("Contrail")


def city(code: str) -> str:
    return airports.get(code=code).city


def served(place: Airport) -> bool:
    return flights.where(destination=place.code).count() > 0


def upcoming() -> vt.Table[Trip]:
    return trips.where(lambda t: t.day >= TODAY).order_by("day")


def lowest(route: vt.Table[Flight], day: date) -> str:
    return money(route.where(day=day).min("fare"))


def tabs() -> vt.Tabs:
    return vt.Tabs({"Home": home(), "Trips": my_trips(), "Profile": profile()})


@app.scene
def home():
    soonest = upcoming().first()
    next_trip = vt.Row(f"San Francisco to {city(soonest.destination)}", long_day(soonest.day), to=trip(soonest))
    return [
        vt.Heading(f"Good morning, {traveler.first_name}"),
        vt.SearchBar("Where to?", to=search()),
        vt.List([next_trip], title="Your next trip"),
        vt.Text(f"{traveler.miles:,} Contrail Miles"),
        tabs(),
    ]


@app.scene
def search():
    options: list[vt.Option] = []
    for place in airports.where(lambda a: a.code != "SFO").order_by("city"):
        go = dates(place) if served(place) else no_flights(place)
        options.append(vt.Option(f"{place.city} ({place.code})", to=go))
    return [vt.SearchBar("Where to?", options=options, no_match=not_found())]


@app.scene
def not_found():
    return [
        vt.Heading("No airport matches"),
        vt.Text("Try a city or a three-letter airport code."),
        vt.Button("Search again", to=search()),
    ]


@app.scene
def no_flights(place: Airport):
    cities = [a.city for a in airports.where(served).order_by("city")]
    return [
        vt.Heading(f"No flights to {place.city}"),
        vt.Text(f"In December, Contrail flies to {joined(cities)}."),
        vt.Button("Search again", to=search()),
    ]


@app.scene
def dates(place: Airport):
    route = flights.where(destination=place.code)
    return [
        vt.Heading(f"San Francisco to {place.city}"),
        vt.Text("Pick a day. Each shows the lowest one-way fare."),
        vt.DatePicker({day: vt.Option(lowest(route, day), to=results(place, day))
                       for day in route.distinct("day")}),
    ]


@app.scene
def results(place: Airport, day: date):
    route = flights.where(destination=place.code)
    return [
        vt.Heading(f"San Francisco to {place.city}"),
        vt.DateStrip({other: vt.Option(lowest(route, other), to=results(place, other))
                      for other in route.distinct("day")}),
        vt.List([vt.Row(times(f), f"{duration(f)}, {stops(f)}", money(f.fare), to=flight(f))
                 for f in route.where(day=day).order_by("departs")]),
    ]


@app.scene
def flight(f: Flight):
    return [
        vt.Heading(f"{f.number} to {city(f.destination)}"),
        vt.Text(long_day(f.day)),
        vt.Text(f"{times(f)}, {duration(f)}, {stops(f)}"),
        vt.Text(f"{f.aircraft}. Earns {f.miles:,} miles."),
        vt.Button(f"Book for {money(f.fare)}", to=booked(f)),
    ]


@app.scene
def booked(f: Flight):
    return [
        vt.Heading("You're booked"),
        vt.Text(f"{f.number} to {city(f.destination)}, {long_day(f.day)}"),
        vt.Text(f"Departs {clock(f.departs)}. Confirmation {confirmation(f)}."),
        vt.Button("Done", to=home()),
    ]


@app.scene
def my_trips():
    recent = trips.where(lambda t: t.day < TODAY).order_by("day", descending=True).limit(3)
    return [
        vt.Heading("Your trips"),
        vt.List([vt.Row(f"San Francisco to {city(t.destination)}", long_day(t.day), to=trip(t))
                 for t in upcoming()], title="Upcoming"),
        vt.List([vt.Row(f"{city(t.origin)} to {city(t.destination)}", short_day(t.day)) for t in recent],
                title="Recent"),
        tabs(),
    ]


@app.scene
def trip(t: Trip):
    return [
        vt.Heading(f"San Francisco to {city(t.destination)}"),
        vt.Text(f"{t.flight}, {long_day(t.day)}"),
        vt.Text(f"Confirmation {t.confirmation}"),
        vt.Text(f"Earns {t.miles:,} miles"),
    ]


@app.scene
def profile():
    by_month = trips.where(lambda t: t.day < TODAY and t.day.year == TODAY.year).group_by(lambda t: t.day.month)
    flown, miles = by_month.count(), by_month.sum("miles")
    running = dict(zip(range(1, 12), accumulate(miles.get(month, 0) for month in range(1, 12))))
    return [
        vt.Heading(traveler.name),
        vt.Text(f"{traveler.status} member, {traveler.miles:,} miles"),
        vt.BarChart("Flights per month since June", {name: flown.get(month, 0) for month, name in SHOWN.items()}),
        vt.LineChart("Miles flown in 2026", {name: running[month] for month, name in SHOWN.items()}),
        tabs(),
    ]
