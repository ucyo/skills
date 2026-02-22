---
name: oebb-scotty
description: Austrian rail travel planner (ÖBB Scotty). Use when planning train journeys in Austria, checking departures/arrivals at stations, or looking for service disruptions. Covers ÖBB trains, S-Bahn, regional trains, and connections to neighboring countries.
---

# Austrian Public Transport API (VAO/HAFAS)

Query Austrian public transport for trip planning, station departures, and service alerts via the public VAO HAFAS API. Covers all of Austria — ÖBB trains, S-Bahn, U-Bahn, trams, and buses.

> **Note:** No API key required. Uses the public VAO endpoint.

## Quick Reference

| Method | Purpose |
|--------|---------|
| `LocMatch` | Search for stations/stops by name |
| `TripSearch` | Plan a journey between two locations |
| `StationBoard` | Get departures/arrivals at a station |
| `HimSearch` | Get service alerts and disruptions |

**Base URL:** `https://vao.demo.hafas.de/gate`

All requests are POST with this base body:

```json
{
  "svcReqL": [{ "req": { ... }, "meth": "METHOD_NAME", "id": "1|1|" }],
  "client": {"id": "VAO", "v": "1", "type": "AND", "name": "nextgen"},
  "ver": "1.73",
  "lang": "de",
  "auth": {"aid": "nextgen", "type": "AID"}
}
```

---

## 1. Location Search (`LocMatch`)

Search for stations, stops, addresses, or POIs by name.

### Request

```bash
curl -s -X POST "https://vao.demo.hafas.de/gate" \
  -H "Content-Type: application/json" \
  -d '{
    "svcReqL": [{
      "req": {"input": {"loc": {"name": "Wien Hbf"}, "field": "S"}},
      "meth": "LocMatch",
      "id": "1|1|"
    }],
    "client": {"id": "VAO", "v": "1", "type": "AND", "name": "nextgen"},
    "ver": "1.73", "lang": "de",
    "auth": {"aid": "nextgen", "type": "AID"}
  }'
```

### Response Structure

```json
{
  "svcResL": [{
    "res": {
      "match": {
        "locL": [{
          "name": "Wien Hauptbahnhof",
          "extId": "490134900",
          "type": "S",
          "crd": { "x": 16377950, "y": 48184986 }
        }]
      }
    }
  }]
}
```

### Key Fields

| Field | Description |
|-------|-------------|
| `extId` | Station ID (use in other queries) |
| `name` | Station name |
| `type` | `S` (Station), `A` (Address), `P` (POI) |
| `crd.x/y` | Coordinates (x=lon, y=lat, scaled by 10^6) |

---

## 2. Trip Search (`TripSearch`)

Plan a journey between two locations.

### Request

```bash
curl -s -X POST "https://vao.demo.hafas.de/gate" \
  -H "Content-Type: application/json" \
  -d '{
    "svcReqL": [{
      "req": {
        "depLocL": [{"extId": "490134900", "type": "S"}],
        "arrLocL": [{"extId": "455000200", "type": "S"}],
        "getPasslist": false,
        "maxChg": 5,
        "numF": 5
      },
      "meth": "TripSearch",
      "id": "1|1|"
    }],
    "client": {"id": "VAO", "v": "1", "type": "AND", "name": "nextgen"},
    "ver": "1.73", "lang": "de",
    "auth": {"aid": "nextgen", "type": "AID"}
  }'
```

To search at a specific time, add to `req`:

```json
"outDate": "20260523",
"outTime": "080000",
"outFrwd": true
```

### Parameters

| Param | Description |
|-------|-------------|
| `depLocL` | Departure location(s) — use `extId` from LocMatch |
| `arrLocL` | Arrival location(s) |
| `outDate` | Departure date (YYYYMMDD) |
| `outTime` | Departure time (HHMMSS) |
| `outFrwd` | `true` = search forward, `false` = search backward |
| `numF` | Number of connections to return |
| `maxChg` | Maximum number of changes |
| `getPasslist` | Include intermediate stops |
| `jnyFltrL` | Product filter (see below) |

### Product Filter

```json
"jnyFltrL": [{"type": "PROD", "mode": "INC", "value": "1023"}]
```

| Bit | Value | Product |
|-----|-------|---------|
| 0 | 1 | ICE/RJX (High-speed) |
| 1 | 2 | IC/EC (InterCity) |
| 2 | 4 | NJ (Night trains) |
| 3 | 8 | D/EN (Express) |
| 4 | 16 | REX/R (Regional Express) |
| 5 | 32 | S-Bahn |
| 6 | 64 | Bus |
| 7 | 128 | Ferry |
| 8 | 256 | U-Bahn |
| 9 | 512 | Tram |

Use `1023` for all products, or sum specific bits.

### Response Structure

```json
{
  "svcResL": [{
    "res": {
      "outConL": [{
        "date": "20260523",
        "dur": "025200",
        "chg": 0,
        "dep": {
          "dTimeS": "075700",
          "dPltfS": {"txt": "8A-B"},
          "locX": 0
        },
        "arr": {
          "aTimeS": "104900",
          "aPltfS": {"txt": "7"},
          "locX": 1
        },
        "secL": [{
          "type": "JNY",
          "jny": {
            "prodX": 0,
            "dirTxt": "Salzburg Hbf"
          },
          "dep": { "dTimeS": "075700" },
          "arr": { "aTimeS": "104900" }
        }]
      }],
      "common": {
        "locL": [...],
        "prodL": [...],
        "dirL": [...]
      }
    }
  }]
}
```

### Key Connection Fields

| Field | Description |
|-------|-------------|
| `dur` | Duration (HHMMSS) |
| `chg` | Number of changes |
| `dTimeS` | Scheduled departure |
| `dTimeR` | Real-time departure (if available) |
| `aTimeS` | Scheduled arrival |
| `aTimeR` | Real-time arrival (if available) |
| `dPltfS.txt` | Departure platform |
| `aPltfS.txt` | Arrival platform |
| `secL` | Journey sections (legs) |
| `secL[].jny.prodX` | Index into `common.prodL[]` for train name |

### Understanding prodX and dirX

- `prodX` is an index into `common.prodL[]` for the train name (e.g., "RJX 662")
- `dirX` is an index into `common.dirL[]` for the direction text
- `locX` is an index into `common.locL[]` for the station name

### Extracting Trip Summaries with jq

```bash
curl -s -X POST "https://vao.demo.hafas.de/gate" \
  -H "Content-Type: application/json" \
  -d '{ ... }' | jq '
    .svcResL[0].res as $r |
    $r.common.prodL as $prods |
    $r.common.locL as $locs |
    [$r.outConL[] | {
      dep: .dep.dTimeS,
      arr: .arr.aTimeS,
      from: $locs[.dep.locX].name,
      to: $locs[.arr.locX].name,
      depPlatform: .dep.dPltfS.txt,
      arrPlatform: .arr.aPltfS.txt,
      dur: .dur,
      chg: .chg,
      legs: [.secL[] | select(.type == "JNY") | {
        train: $prods[.jny.prodX].name,
        from: $locs[.dep.locX].name,
        to: $locs[.arr.locX].name,
        dep: .dep.dTimeS,
        arr: .arr.aTimeS
      }]
    }]'
```

---

## 3. Station Board (`StationBoard`)

Get departures or arrivals at a station.

### Request

```bash
curl -s -X POST "https://vao.demo.hafas.de/gate" \
  -H "Content-Type: application/json" \
  -d '{
    "svcReqL": [{
      "req": {
        "stbLoc": {"extId": "490134900", "type": "S"},
        "type": "DEP",
        "maxJny": 20
      },
      "meth": "StationBoard",
      "id": "1|1|"
    }],
    "client": {"id": "VAO", "v": "1", "type": "AND", "name": "nextgen"},
    "ver": "1.73", "lang": "de",
    "auth": {"aid": "nextgen", "type": "AID"}
  }'
```

To query at a specific time, add to `req`:

```json
"date": "20260523",
"time": "080000"
```

### Parameters

| Param | Description |
|-------|-------------|
| `stbLoc` | Station — use `extId` from LocMatch |
| `type` | `DEP` (departures) or `ARR` (arrivals) |
| `maxJny` | Maximum number of journeys |
| `date` | Date (YYYYMMDD) |
| `time` | Time (HHMMSS) |

### Response Structure

```json
{
  "svcResL": [{
    "res": {
      "jnyL": [{
        "prodX": 0,
        "dirTxt": "Salzburg Hbf",
        "stbStop": {
          "dTimeS": "080000",
          "dTimeR": "080200",
          "dPlatfS": "8A-B",
          "dCncl": false
        }
      }],
      "common": {
        "prodL": [{"name": "RJX 662"}],
        "dirL": [{"txt": "Salzburg Hbf"}]
      }
    }
  }]
}
```

### Key Fields

| Field | Description |
|-------|-------------|
| `prodX` | Index into `common.prodL[]` for train/line name |
| `dirTxt` or `dirX` | Direction (dirX indexes into `common.dirL[]`) |
| `dTimeS` / `dTimeR` | Scheduled / real-time departure |
| `dPlatfS` | Platform |
| `dCncl` | `true` if cancelled |

### Extracting Departures with jq

```bash
curl -s -X POST "https://vao.demo.hafas.de/gate" \
  -H "Content-Type: application/json" \
  -d '{ ... }' | jq '
    .svcResL[0].res as $r |
    $r.common.prodL as $prods |
    $r.common.dirL as $dirs |
    [$r.jnyL[] | {
      line: $prods[.prodX].name,
      direction: (if .dirX then $dirs[.dirX].txt else .dirTxt end),
      scheduled: .stbStop.dTimeS,
      realtime: .stbStop.dTimeR,
      platform: .stbStop.dPlatfS,
      cancelled: .stbStop.dCncl
    }]'
```

---

## 4. Service Alerts (`HimSearch`)

Get current disruptions and service information.

### Request

```bash
curl -s -X POST "https://vao.demo.hafas.de/gate" \
  -H "Content-Type: application/json" \
  -d '{
    "svcReqL": [{
      "req": {
        "maxNum": 20,
        "himFltrL": [{"mode": "INC", "type": "HIMCAT", "value": "*"}]
      },
      "meth": "HimSearch",
      "id": "1|1|"
    }],
    "client": {"id": "VAO", "v": "1", "type": "AND", "name": "nextgen"},
    "ver": "1.73", "lang": "de",
    "auth": {"aid": "nextgen", "type": "AID"}
  }'
```

### Response Structure

```json
{
  "svcResL": [{
    "res": {
      "common": {
        "himL": [{
          "hid": "HIM_FREETEXT_843858",
          "cat": 1,
          "prio": 0,
          "head": "Schienenersatzverkehr",
          "text": "Wegen Bauarbeiten...",
          "sDate": "20260520",
          "eDate": "20260525"
        }]
      }
    }
  }]
}
```

---

## Common Station IDs

| Station | extId |
|---------|-------|
| Wien Hauptbahnhof | 490134900 |
| Wien Westbahnhof | 490024300 |
| Wien Praterstern | 490056100 |
| Wien Karlsplatz | 490024600 |
| Wien Stephansplatz | 490132000 |
| Wien Schwedenplatz | 490119500 |
| Salzburg Hbf | 455000200 |
| Linz Hbf | 444116400 |
| Graz Hbf | 460086000 |
| Innsbruck Hbf | 481070100 |
| Klagenfurt Hbf | 492019500 |
| St. Pölten Hbf | 431543300 |
| Wiener Neustadt Hbf | 430521000 |
| Krems a.d. Donau | 431046400 |

**Tip:** Always use LocMatch to find the correct station ID.

---

## Time Format

- Dates: `YYYYMMDD` (e.g., `20260523`)
- Times: `HHMMSS` (e.g., `080000` = 08:00:00)
- Duration: `HHMMSS` (e.g., `025200` = 2h 52m)

---

## Transport Types

| Code | Type |
|------|------|
| ICE/RJ/RJX | High-speed trains |
| IC/EC | InterCity/EuroCity |
| NJ | Nightjet |
| REX/R | Regional Express/Regional |
| S | S-Bahn (suburban rail) |
| U | U-Bahn (Vienna metro) |
| STR | Tram/Strassenbahn |
| BUS | Bus |
| AST | Demand-responsive transport |

---

## Error Handling

Check `err` field in response:

```json
{
  "err": "OK",
  "err": "PARSE",
  "err": "NO_MATCH",
  "errTxt": "..."
}
```

---

## Notes

- This API covers all Austrian public transport, not just ÖBB
- Cross-border routes to Germany, Czech Republic, Hungary, etc. are included
- Real-time data is available when provided by the operator
- No API key required — uses the public VAO endpoint
- Source: [VOR AnachB](https://anachb.vor.at/) / HAFAS
