---
name: deutsche-bahn
description: German rail travel planner (Deutsche Bahn). Use when planning train journeys in Germany, checking departures/arrivals at stations, or looking for service disruptions. Covers ICE, IC/EC, RE, RB, S-Bahn, and connections to neighboring countries.
---

# Deutsche Bahn API (bahn.de)

Query Germany's public transport for trip planning, station departures/arrivals, and journey details via the bahn.de web API.

> **Note:** The old HAFAS mgate.exe endpoint (`reiseauskunft.bahn.de`) was permanently shut down. This skill uses the new "vendo"/"movas" API at `int.bahn.de`. No API key required.

## Quick Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/reiseloesung/orte` | GET | Search for stations/stops by name |
| `/angebote/fahrplan` | POST | Plan a journey between two locations |
| `/reiseloesung/abfahrten` | GET | Get departures at a station |
| `/reiseloesung/ankuenfte` | GET | Get arrivals at a station |

**Base URL:** `https://int.bahn.de/web/api`

**Important:** All requests must use `--compressed` with curl (responses are gzip-encoded).

---

## 1. Location Search

Search for stations, stops, addresses, or POIs by name.

### Request

```bash
curl -s --compressed "https://int.bahn.de/web/api/reiseloesung/orte?suchbegriff=Berlin%20Hbf&limit=10"
```

### Parameters

| Param | Description |
|-------|-------------|
| `suchbegriff` | Search term (URL-encoded) |
| `limit` | Maximum number of results |

### Response

```json
[
  {
    "extId": "8011160",
    "id": "A=1@O=Berlin Hbf@X=13369549@Y=52525589@U=80@L=8011160@",
    "lat": 52.524925,
    "lon": 13.369629,
    "name": "Berlin Hbf",
    "products": ["ICE", "EC_IC", "IR", "REGIONAL", "SBAHN", "BUS", "UBAHN", "TRAM"],
    "type": "ST"
  }
]
```

### Key Fields

| Field | Description |
|-------|-------------|
| `extId` | Station ID (use in departures/arrivals) |
| `id` | Location ID string (use as `lid` in journey search) |
| `name` | Station name |
| `lat/lon` | Coordinates |
| `type` | `ST` (station), `ADR` (address), `POI` (point of interest) |

---

## 2. Journey Search

Plan a journey between two locations.

### Request

```bash
curl -s --compressed -X POST "https://int.bahn.de/web/api/angebote/fahrplan" \
  -H "Content-Type: application/json" \
  -d '{
    "abfahrtsHalt": "A=1@O=Berlin Hbf@L=8011160@",
    "ankunftsHalt": "A=1@O=München Hbf@L=8000261@",
    "anfrageZeitpunkt": "2026-02-23T08:00:00",
    "ankunftSuche": "ABFAHRT",
    "klasse": "KLASSE_2",
    "reisende": [
      {
        "typ": "ERWACHSENER",
        "anzahl": 1,
        "alter": [],
        "ermaessigungen": [{"art": "KEINE_ERMAESSIGUNG", "klasse": "KLASSENLOS"}]
      }
    ],
    "schnelleVerbindungen": true,
    "sitzplatzOnly": false,
    "reservierungsKontingenteVorhanden": false
  }'
```

### Parameters

| Param | Description |
|-------|-------------|
| `abfahrtsHalt` | Departure location `id` (from location search) |
| `ankunftsHalt` | Arrival location `id` |
| `anfrageZeitpunkt` | Date/time in ISO format (`YYYY-MM-DDTHH:MM:SS`) |
| `ankunftSuche` | `ABFAHRT` (search by departure) or `ANKUNFT` (search by arrival) |
| `klasse` | `KLASSE_1` (first class) or `KLASSE_2` (second class) |
| `reisende` | Array of travellers (see below) |
| `schnelleVerbindungen` | `true` for fast connections only |
| `produktgattungen` | Filter by transport type (see product filter) |

### Traveller Types

| Type | Description |
|------|-------------|
| `ERWACHSENER` | Adult |
| `KIND` | Child (set `alter` array, e.g. `["10"]`) |
| `KLEINKIND` | Infant |
| `JUGENDLICHER` | Youth |
| `SENIOR` | Senior |

### Discount Cards (ermaessigungen)

| Art | Description |
|-----|-------------|
| `KEINE_ERMAESSIGUNG` | No discount |
| `BAHNCARD25` | BahnCard 25 |
| `BAHNCARD50` | BahnCard 50 |
| `BAHNCARD100` | BahnCard 100 |

### Product Filter (produktgattungen)

Filter by transport types. Omit to include all.

```json
"produktgattungen": ["ICE", "EC_IC", "IR", "REGIONAL", "SBAHN"]
```

| Value | Product |
|-------|---------|
| `ICE` | ICE (high-speed) |
| `EC_IC` | IC/EC (InterCity/EuroCity) |
| `IR` | InterRegio |
| `REGIONAL` | RE/RB (regional) |
| `SBAHN` | S-Bahn |
| `BUS` | Bus |
| `SCHIFF` | Ferry |
| `UBAHN` | U-Bahn |
| `TRAM` | Tram |
| `ANRUFPFLICHTIG` | On-demand transport |

### Response Structure

```json
{
  "verbindungen": [
    {
      "tripId": "...",
      "verbindungsAbschnitte": [
        {
          "abfahrtsZeitpunkt": "2026-02-23T08:36:00",
          "abfahrtsOrt": "Berlin Hbf",
          "abfahrtsOrtExtId": "8011160",
          "ankunftsZeitpunkt": "2026-02-23T12:46:00",
          "ankunftsOrt": "München Hbf",
          "ankunftsOrtExtId": "8000261",
          "verkehrsmittel": {
            "name": "ICE 1005",
            "produktGattung": "ICE",
            "kategorie": "ICE",
            "nummer": "1005",
            "richtung": "München Hbf",
            "kurzText": "ICE",
            "mittelText": "ICE 1005",
            "langText": "ICE 1005",
            "zugattribute": [...]
          },
          "halte": [...],
          "auslastungsmeldungen": [...]
        }
      ],
      "umstiegsAnzahl": 0,
      "verbindungsDauerInSeconds": 14400,
      "angebotsPreis": {"betrag": 29.90, "waehrung": "EUR"},
      "himMeldungen": [...]
    }
  ]
}
```

### Key Connection Fields

| Field | Description |
|-------|-------------|
| `verbindungsAbschnitte` | Journey legs (array) |
| `umstiegsAnzahl` | Number of changes |
| `verbindungsDauerInSeconds` | Total duration in seconds |
| `angebotsPreis` | Price (if available) |
| `himMeldungen` | Service messages/disruptions |

### Key Leg Fields

| Field | Description |
|-------|-------------|
| `abfahrtsZeitpunkt` | Departure time (ISO format) |
| `ankunftsZeitpunkt` | Arrival time (ISO format) |
| `abfahrtsOrt` / `ankunftsOrt` | Station names |
| `abfahrtsOrtExtId` / `ankunftsOrtExtId` | Station IDs |
| `verkehrsmittel.name` | Train name (e.g., "ICE 1005") |
| `verkehrsmittel.produktGattung` | Product type |
| `halte` | Intermediate stops |
| `auslastungsmeldungen` | Occupancy information |

### Extracting Journey Summaries with jq

```bash
curl -s --compressed -X POST "https://int.bahn.de/web/api/angebote/fahrplan" \
  -H "Content-Type: application/json" \
  -d '{ ... }' | jq '
    [.verbindungen[] | {
      changes: .umstiegsAnzahl,
      duration_min: (.verbindungsDauerInSeconds / 60 | floor),
      price: .angebotsPreis.betrag,
      legs: [.verbindungsAbschnitte[] | {
        train: .verkehrsmittel.name,
        from: .abfahrtsOrt,
        to: .ankunftsOrt,
        dep: .abfahrtsZeitpunkt,
        arr: .ankunftsZeitpunkt
      }]
    }]'
```

---

## 3. Departures

Get departures at a station.

### Request

```bash
curl -s --compressed "https://int.bahn.de/web/api/reiseloesung/abfahrten?ortExtId=8011160&datum=2026-02-23&zeit=08:00:00&verkehrsmittel[]=ICE&verkehrsmittel[]=EC_IC"
```

### Parameters

| Param | Description |
|-------|-------------|
| `ortExtId` | Station ID (from location search) |
| `datum` | Date (`YYYY-MM-DD`) |
| `zeit` | Time (`HH:MM:SS`) |
| `verkehrsmittel[]` | Product filter (repeatable, see product values) |

### Response Structure

```json
{
  "entries": [
    {
      "bahnhofsId": "8098160",
      "zeit": "2026-02-23T08:36:00",
      "ezZeit": "2026-02-23T08:38:00",
      "gleis": "6",
      "journeyId": "...",
      "verkehrmittel": {
        "name": "ICE 1005",
        "kurzText": "ICE",
        "mittelText": "ICE 1005",
        "langText": "ICE 1005",
        "produktGattung": "ICE"
      },
      "meldungen": [
        {
          "prioritaet": "NIEDRIG",
          "text": "Es wird eine hohe Auslastung erwartet."
        }
      ]
    }
  ]
}
```

### Key Fields

| Field | Description |
|-------|-------------|
| `zeit` | Scheduled time |
| `ezZeit` | Real-time estimate (if available) |
| `gleis` | Platform |
| `verkehrmittel.name` | Train name |
| `meldungen` | Service messages (delays, occupancy, etc.) |

---

## 4. Arrivals

Get arrivals at a station.

### Request

```bash
curl -s --compressed "https://int.bahn.de/web/api/reiseloesung/ankuenfte?ortExtId=8011160&datum=2026-02-23&zeit=08:00:00&verkehrsmittel[]=ICE"
```

Same parameters and response structure as departures.

---

## Common Station IDs

| Station | extId |
|---------|-------|
| Berlin Hbf | 8011160 |
| Berlin Ostbahnhof | 8010255 |
| Berlin Südkreuz | 8011113 |
| München Hbf | 8000261 |
| Hamburg Hbf | 8002549 |
| Frankfurt (Main) Hbf | 8000105 |
| Köln Hbf | 8000207 |
| Stuttgart Hbf | 8000096 |
| Düsseldorf Hbf | 8000085 |
| Hannover Hbf | 8000152 |
| Nürnberg Hbf | 8000284 |
| Leipzig Hbf | 8010205 |
| Dresden Hbf | 8010085 |
| Dortmund Hbf | 8000080 |
| Essen Hbf | 8000098 |
| Bremen Hbf | 8000050 |
| Mannheim Hbf | 8000244 |
| Karlsruhe Hbf | 8000191 |
| Freiburg (Breisgau) Hbf | 8000107 |
| Augsburg Hbf | 8000013 |

---

## Time Format

- Dates: `YYYY-MM-DD` (e.g., `2026-02-23`)
- Times: `HH:MM:SS` (e.g., `08:00:00`)
- Timestamps: ISO 8601 (`2026-02-23T08:00:00`)
- Durations: in seconds (`verbindungsDauerInSeconds`)

---

## Error Handling

HTTP status codes indicate errors. The API may return JSON error bodies:

```json
{
  "fehpielerTyp": "TECHNISCH",
  "fehpielerMeldungen": ["..."]
}
```

Common issues:
- `404` — station not found or invalid endpoint
- `500` — malformed request body
- Empty `verbindungen` array — no connections found for the given criteria

---

## Notes

- The old HAFAS endpoint (`reiseauskunft.bahn.de/bin/mgate.exe`) is permanently offline
- This API is the same one used by [bahn.de](https://int.bahn.de)
- Responses are gzip-compressed — always use `curl --compressed`
- Rate limiting: aggressive blocking may occur with high request volume
- Source: [db-vendo-client](https://github.com/public-transport/db-vendo-client) for full API details
