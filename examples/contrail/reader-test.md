# Reader test

`scripts/reader-test` sent only `contrail/screenplay.py` to claude-opus-5-5 and asked what the app does. A second call checked that answer against the features in `README.md`. The answer states 9 of 9.

## What the app does, read from the screenplay alone

# Contrail: what the app does, scene by scene

Contrail lets someone book a one-way flight out of San Francisco, see their upcoming and recent trips, and view their member profile. The app treats "today" as **1 December 2026**.

## Home (where the app opens)

**Shows:**
- A greeting, "Good morning, *first name*". It always says "morning".
- A **"Where to?"** search bar.
- A "Your next trip" list with one row: "San Francisco to *city*" and the date of the soonest trip dated today or later.
- The traveler's Contrail Miles balance.
- Tabs: **Home**, **Trips**, **Profile**.

**Presses:**
- **Search bar** → Search.
- **Next-trip row** → Trip details for that trip.
- **Trips tab** → Your trips. **Profile tab** → Profile.

The file doesn't handle the case where there is no upcoming trip. It always tries to build the next-trip row.

## Search

**Shows:** a "Where to?" search bar listing every airport except SFO, alphabetized by city, as "*City* (*CODE*)". Typing a city or airport code narrows the list.

**Presses:**
- **An airport Contrail flies to** → Pick a date for that airport.
- **An airport with no flights** → No flights.
- **Text that matches no airport** → No airport matches.

## No airport matches

**Shows:** "No airport matches" and "Try a city or a three-letter airport code."

**Presses:** **Search again** → Search.

## No flights

**Shows:** "No flights to *city*", then "In December, Contrail flies to *…*" with the list of cities that have flights.

**Presses:** **Search again** → Search.

## Pick a date

**Shows:**
- The heading "San Francisco to *city*".
- "Pick a day. Each shows the lowest one-way fare."
- A date picker offering only the days that have flights on this route, each labeled with that day's lowest fare.

**Presses:** **A day** → Results for that city and day.

## Results

**Shows:**
- The heading "San Francisco to *city*".
- A strip of the route's available days, each with its lowest fare.
- That day's flights, ordered by departure time. Each row shows departure and arrival times, duration, number of stops and fare.

**Presses:**
- **Another day in the strip** → Results for that day.
- **A flight row** → Flight details.

## Flight details

**Shows:**
- Flight number and destination city.
- The date.
- Times, duration and stops.
- The aircraft and the miles the flight earns.

**Presses:** **Book for *fare*** → You're booked.

## You're booked

**Shows:**
- "You're booked".
- Flight number, destination and date.
- Departure time and a confirmation code.

**Presses:** **Done** → Home.

This file doesn't support any of the following around booking:
- No payment or passenger-details step.
- No saving of the booking.
- No change to the miles balance.
- Nothing suggests the new flight will appear under Trips.

## Your trips (Trips tab)

**Shows:**
- **Upcoming:** every trip dated today or later, soonest first. Each row reads "San Francisco to *city*" with the date.
- **Recent:** the three most recent past trips, newest first. Each row reads "*origin* to *destination*" with a short date.
- The tabs.

**Presses:**
- **An upcoming trip** → Trip details.
- **A recent trip** → nothing; these rows aren't linked.
- **Tabs** → Home or Profile.

## Trip details

**Shows:**
- "San Francisco to *city*".
- Flight number and date.
- The confirmation code.
- The miles the trip earns.

**Presses:** none. This file gives the scene no buttons or tabs. Any way back would have to come from the framework.

## Profile (Profile tab)

**Shows:**
- The traveler's name, status tier and miles balance.
- A bar chart, "Flights per month since June": the number of past trips flown in each month from June to November 2026.
- A line chart, "Miles flown in 2026", plotted for June to November. It is a running total that starts in January, so its June point already includes January–May miles.
- The tabs.

**Presses:** **Tabs** → Home or Trips.

## The answer against each feature

1. **Yes.** Home greets the traveler and shows their next trip and their miles. A search bar asks "Where to?".

   Home shows a greeting with the first name, a "Where to?" search bar, the next trip row and the miles balance.

2. **Yes.** Search finds a destination by typing a city or airport code, or by picking it from a list.

   Search lists every airport by city and code, and typing a city or code narrows the list. Picking an airport from the list proceeds to the next step.

3. **Yes.** A month calendar shows the lowest fare on every day with flights. Other days can't be picked.

   The date picker offers only the days with flights on the route, each labeled with that day's lowest fare. The look (a month calendar) can't be asked of a screenplay, and the behavior is all described.

4. **Yes.** The day's flights are listed by departure time, with times, duration, stops, and fare. A row of the other days shows their lowest fares, and picking one switches the day.

   Results lists flights by departure time with times, duration, stops and fare. A strip of available days shows their lowest fares, and pressing another day switches the results to it.

5. **Yes.** A flight shows its day, times, aircraft, and the miles it earns.

   Flight details shows the date, times, aircraft and the miles the flight earns.

6. **Yes.** One button books it and shows a confirmation code.

   The single button "Book for fare" leads to You're booked, which shows a confirmation code.

7. **Yes.** Trips lists the upcoming trips, which open to their details, and the three most recent trips.

   Trips lists upcoming trips that open to Trip details, plus the three most recent past trips.

8. **Yes.** Profile shows the traveler's status and miles, a bar chart of flights per month, and a line chart of the miles flown this year.

   Profile shows status tier, miles, a flights-per-month bar chart and a 2026 miles-flown line chart.

9. **Yes.** A search that matches no airport says so. A city with no flights says which cities have them.

   No airport matches says so. No flights lists the cities that do have flights.

## Tokens and cost

- read   claude-opus-5-5: 2,423 input tokens, 1,944 output tokens, $0.0486
- check  claude-opus-5-5: 3,030 input tokens, 493 output tokens, $0.0220
- total  $0.0706
