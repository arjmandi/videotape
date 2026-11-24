# Contrail

Contrail is a flight booking demo written as a Videotape screenplay. It books one-way flights from San Francisco for one demo traveler.

## Features

1. Home greets the traveler and shows their next trip and their miles. A search bar asks "Where to?".
2. Search finds a destination by typing a city or airport code, or by picking it from a list.
3. A month calendar shows the lowest fare on every day with flights. Other days can't be picked.
4. The day's flights are listed by departure time, with times, duration, stops, and fare. A row of the other days shows their lowest fares, and picking one switches the day.
5. A flight shows its day, times, aircraft, and the miles it earns.
6. One button books it and shows a confirmation code.
7. Trips lists the upcoming trips, which open to their details, and the three most recent trips.
8. Profile shows the traveler's status and miles, a bar chart of flights per month, and a line chart of the miles flown this year.
9. A search that matches no airport says so. A city with no flights says which cities have them.

## Build it

The repository's [developer's guide](../../docs/guide.md), and it builds Contrail from an empty folder. Its whole files are this folder's files, and `tests/test_guide.py` holds the two together. This folder's `pyproject.toml` renders with the stand-in, so a render here costs nothing.
