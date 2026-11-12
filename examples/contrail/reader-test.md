# Reader test

`scripts/reader-test` sent only `contrail/screenplay.py` to claude-opus-5-5 and asked what the app does. A second call checked that answer against the features in `README.md`. The answer states 8 of 9.

## What the app does, read from the screenplay alone

# Contrail: what the app does for its user

Contrail is a flight-booking app for one traveler. It books **one-way flights out of San Francisco** and also shows the person their trips and their flying history. The app treats "today" as **1 December 2026**. That date is fixed in the code, so "upcoming" and "recent" are always measured from it.

Three scenes (Home, Trips, Profile) end with a **tab bar** with tabs labelled *Home*, *Trips* and *Profile*, each going to the scene of that name. The other scenes have no tabs and no explicit back button. Whether the framework provides a back gesture isn't visible from this file.

---

## 1. Home (where the app opens)

**Shows:**
- A greeting: "Good morning, *first name*". It always says "morning".
- A "Where to?" search bar.
- A list titled "Your next trip" with one row. The row reads "San Francisco to *city*" and gives the date of the soonest trip dated on or after 1 Dec 2026.
- The traveler's Contrail Miles balance, e.g. "12,345 Contrail Miles".
- The tab bar.

**Presses:**
- **Search bar** → Search.
- **Next-trip row** → Trip details for that trip.
- **Tabs** → Home / Trips / Profile.

*Note:* nothing here handles the case of having no upcoming trip. What happens then depends on code not shown.

## 2. Search

**Shows:** A "Where to?" search bar offering every airport except SFO. The airports are sorted by city and labelled "City (CODE)".

**Presses:**
- **An airport that has flights to it** → Pick a date for that airport.
- **An airport with no flights to it** → No flights.
- **A search that matches nothing** → No airport matches.

## 3. No airport matches

**Shows:**
- The heading "No airport matches".
- The hint "Try a city or a three-letter airport code."

**Presses:** **Search again** → Search.

## 4. No flights

**Shows:**
- The heading "No flights to *city*".
- The sentence "In December, Contrail flies to …", followed by every city that does have flights, alphabetically. The word "December" is fixed text, not worked out from the flight data.

**Presses:** **Search again** → Search.

## 5. Pick a date

**Shows:**
- The heading "San Francisco to *city*".
- The instruction "Pick a day. Each shows the lowest one-way fare."
- A date picker. Only days with a flight to that city can be chosen, and each one is labelled with that day's lowest fare.

**Presses:** **A day** → Results for that city and day.

## 6. Results

**Shows:**
- The heading "San Francisco to *city*".
- A strip of the same flight days, each with its lowest fare.
- A list of that day's flights, earliest departure first. Each row shows:
  - departure and arrival times,
  - duration and number of stops,
  - fare.

**Presses:**
- **Another day in the strip** → Results for that day.
- **A flight row** → Flight details.

## 7. Flight details

**Shows:**
- The heading "*flight number* to *city*".
- The full date.
- Times, duration and stops.
- The aircraft and the miles the flight earns.

**Presses:** **"Book for *fare*"** → You're booked.

There is no step for passenger details, seat choice or payment. One press books the flight.

## 8. You're booked

**Shows:**
- The heading "You're booked".
- The flight number, destination and date.
- The departure time.
- A confirmation code.

**Presses:** **Done** → Home.

*Note:* nothing in this file adds the booking to the traveler's trips. Whether it later appears on Home or in Trips depends on code not shown.

## 9. Trips

**Shows:**
- **Upcoming:** every trip dated on or after 1 Dec 2026, soonest first. Each row reads "San Francisco to *city*" with the full date.
- **Recent:** the last three past trips, newest first. Each row reads "*origin city* to *destination city*" with a short date.
- The tab bar.

**Presses:**
- **An upcoming trip** → Trip details.
- **Recent rows** lead nowhere.
- **Tabs** → Home / Trips / Profile.

## 10. Trip details

**Shows:**
- The heading "San Francisco to *city*". It always says San Francisco, whatever the trip's recorded origin.
- The flight number and date.
- The confirmation code.
- The miles earned.

**Presses:** none. There is no cancel, change or button of any kind, and no tab bar.

## 11. Profile

**Shows:**
- The traveler's full name.
- Their status and miles balance, e.g. "Gold member, 12,345 miles".
- A bar chart titled "Flights per month in 2026", covering January to November, built from past trips.
- A line chart titled "Miles flown in 2026", showing miles accumulating month by month from January to November.
- The tab bar.

**Presses:** **Tabs** → Home / Trips / Profile.

*Note:* the charts group past trips by calendar month only, not by year. Any trips before 2026 would be counted into the "2026" months.

---

## In short

The person can:
- search for a destination,
- pick a day by lowest fare,
- choose a flight and book it in one tap,
- check their upcoming and recent trips,
- see a profile with their status, miles and monthly flying charts.

Nothing in this file lets them:
- fly from anywhere other than San Francisco,
- book a round trip,
- enter passenger or payment details,
- cancel or change a trip.

## The answer against each feature

1. **Yes.** Home greets the traveler and shows their next trip and their miles. A search bar asks "Where to?".

   Home has a greeting, a 'Where to?' search bar, a 'Your next trip' row and the Contrail Miles balance.

2. **Yes.** Search finds a destination by typing a city or airport code, or by picking it from a list.

   The search bar offers every airport except SFO as a sorted list labelled 'City (CODE)'. The hint 'Try a city or a three-letter airport code' implies typing either one.

3. **No.** A month calendar shows the lowest fare on every day with flights. Other days can't be picked.

   The answer describes a date picker where only flight days can be chosen, each labelled with its lowest fare. It never says it is a month calendar.

4. **Yes.** The day's flights are listed by departure time, with times, duration, stops, and fare. A row of the other days shows their lowest fares, and picking one switches the day.

   Results lists the day's flights earliest first, with times, duration, stops and fare. A strip of the flight days shows lowest fares, and tapping another day switches to it.

5. **Yes.** A flight shows its day, times, aircraft, and the miles it earns.

   Flight details shows the full date, times, duration, stops, aircraft and the miles earned.

6. **Yes.** One button books it and shows a confirmation code.

   A single 'Book for fare' button books the flight. The 'You're booked' screen then shows a confirmation code.

7. **Yes.** Trips lists the upcoming trips, which open to their details, and the three most recent trips.

   Trips shows upcoming trips, which open Trip details, and the last three past trips.

8. **Yes.** Profile shows the traveler's status and miles, a bar chart of flights per month, and a line chart of the miles flown this year.

   Profile shows status and miles, a bar chart of flights per month in 2026, and a line chart of miles flown in 2026, which is the current year.

9. **Yes.** A search that matches no airport says so. A city with no flights says which cities have them.

   The 'No airport matches' screen covers a search with no match. The 'No flights to city' screen lists the cities that do have flights.

## Tokens and cost

- read   claude-opus-5-5: 2,361 input tokens, 2,784 output tokens, $0.0651
- check  claude-opus-5-5: 3,410 input tokens, 825 output tokens, $0.0301
- total  $0.0953
