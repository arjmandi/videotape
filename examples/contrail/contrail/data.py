"""Contrail's data: the airports, the flights on sale, and the demo traveler's trips."""

from datetime import date, time

import videotape as vt


class Airport(vt.Record, key="code"):
    code: str
    city: str
    name: str


class Flight(vt.Record, key=("number", "day")):
    number: str
    origin: str
    destination: str
    day: date
    departs: time
    arrives: time
    minutes: int
    stops: int
    aircraft: str
    fare: int
    miles: int


class Trip(vt.Record, key=("flight", "day")):
    flight: str
    origin: str
    destination: str
    day: date
    miles: int
    confirmation: str


class Traveler(vt.Record):
    name: str
    first_name: str
    miles: int
    status: str


airports = vt.table(Airport, "data/airports.json")
flights = vt.table(Flight, "data/flights.json")
trips = vt.table(Trip, "data/trips.json")
traveler = vt.one(Traveler, "data/traveler.json")
