# Cache Visualizer

[![CI](https://github.com/adyasha-official/cache-visualizer/actions/workflows/ci.yml/badge.svg)](https://github.com/adyasha-official/cache-visualizer/actions/workflows/ci.yml)
![C++17](https://img.shields.io/badge/C%2B%2B-17-blue)
![Python](https://img.shields.io/badge/Python-Flask-green)
![React](https://img.shields.io/badge/React-Vite-61dafb)

**Watch an LRU or LFU cache work, one request at a time.** Type in a request stream, pick a capacity, and step through it to see every hit, miss, eviction and the cache contents after each request. Run the same stream through both policies side by side to see which one wins.

The cache logic is written in C++ with a hand-written doubly linked list. Flask is a thin API around it, and a React app draws the results. Nothing is simulated in the browser: every number on screen comes from the C++ engine.

![LRU vs LFU side by side](docs/screenshots/compare.png)

## Contents

[Why](#why-this-project) · [Features](#features) · [Quick start](#quick-start) · [Deployment](#deployment) · [How it works](#how-it-works) · [API](#api) · [Complexity](#complexity) · [Testing](#testing) · [Future improvements](#future-improvements)

## Why this project

Caches are small, so something has to be thrown out when they fill up. Which item goes depends on the policy:

- **LRU** (least recently used) evicts the item that was used *longest ago*.
- **LFU** (least frequently used) evicts the item used *least often*, and if several are tied, the least recently used among them.

Neither is better on every workload. For example, with capacity 2 and the stream `A A B C A`, LFU keeps the popular `A` and gets 2 hits (40%), while LRU throws it out and gets 1 (20%). On the sample stream `A B C A D B A C D E` with capacity 3, they tie at 2 hits out of 10. This project makes that difference visible on any stream you type in.

## Features

- LRU and LFU, both with O(1) average `get`, `put` and eviction
- Configurable capacity and request stream
- For every request: HIT or MISS, which key was evicted, and the cache contents
- Running statistics: hits, misses, evictions, hit ratio
- Step through with Prev / Next / Reset / End, a slider, autoplay, or click any item in the request history
- **Compare both**: the same stream through LRU and LFU in lockstep, with a comparison table
- Input validation and size limits in the API, with clear error messages
- Tests at every layer, CI on every push, and a Docker image ready to deploy

![LRU after 5 requests of the sample stream](docs/screenshots/lru-step.png)

## Quick start

You need a C++17 compiler (`g++` 7 or newer), Python 3.9+ and Node 18+.

**Linux / macOS**

```bash
make build                              # builds the C++ engine
pip install -r backend/requirements.txt
cd frontend && npm install && cd ..

make run-backend                        # terminal 1: Flask on http://127.0.0.1:5000
make run-frontend                       # terminal 2: Vite on http://localhost:5173
```

**Windows** (PowerShell, no WSL needed). Use a recent MinGW-w64 `g++`, for example `winget install BrechtSanders.WinLibs.POSIX.UCRT`; old MinGW 6.x cannot build C++17.

```powershell
mkdir cpp\build
g++ -std=c++17 -O2 -static -Icpp/include cpp/src/main.cpp cpp/src/doubly_linked_list.cpp cpp/src/lru_cache.cpp cpp/src/lfu_cache.cpp cpp/src/cache_factory.cpp cpp/src/simulator.cpp cpp/src/json_output.cpp -o cpp/build/cache_sim.exe
pip install -r backend\requirements.txt
cd frontend; npm install; cd ..

# terminal 1
cd backend; python app.py
# terminal 2
cd frontend; npm run dev
```

Open **http://localhost:5173**, click **Run Simulation**, and use the step controls. The backend finds `cache_sim.exe` automatically.

You can also use the engine directly:

```bash
echo "A B C A D B A C D E" | cpp/build/cache_sim --policy LRU,LFU --capacity 3
```

## Deployment

The `Dockerfile` builds the React app and the C++ engine and runs everything behind gunicorn on a single port. Flask serves both the website and the API from the same address, so there is nothing else to configure and there are no secrets.

```bash
docker build -t cache-visualizer .
docker run -p 8000:8000 cache-visualizer     # open http://localhost:8000
```

**Deploy on Render (free)**

1. Push this repository to GitHub.
2. In the Render dashboard choose **New → Blueprint** and select the repository.
3. Apply. `render.yaml` sets up the service and its health check (`/api/health`).

The free plan sleeps when idle, so the first request after a quiet period can take about a minute. The container reads the `PORT` environment variable (default 8000).

## How it works

```
React (Vite)
    │  HTTP / JSON
    ▼
Flask API ── validates input, serves the built website in production
    │  runs the engine as a subprocess, JSON out
    ▼
cache_sim (C++ command line program)
    │
    ▼
Simulator ──► Cache interface
                 ┌──────┴──────┐
                 ▼             ▼
                LRU           LFU
                 └──────┬──────┘
                        ▼
                  Steps + Statistics
```

```
cache-visualizer/
├── cpp/
│   ├── include/   node.h, doubly_linked_list.h, cache.h, lru_cache.h, lfu_cache.h, simulator.h
│   ├── src/       implementations, JSON output, main.cpp (command line program)
│   └── tests/     one test program per component
├── backend/       app.py (API), engine.py (bridge to the C++ program), test_api.py
├── frontend/      Vite + React app
├── Dockerfile, render.yaml, .github/workflows/ci.yml
└── docs/screenshots/
```

Flask passes the request stream to `cache_sim` on stdin and the options as a list of arguments (never through a shell), then returns the engine's JSON. Keeping the logic in C++ and the API thin means the engine can be tested without any web stack.

### LRU

A hash map `key → Node*` plus a doubly linked list with `HEAD` and `TAIL` sentinels, ordered most recently used → least recently used.

- `get`: look up the node and move it to the front.
- `put` on an existing key: update the value and move it to the front.
- `put` on a new key when full: remove the node before `TAIL`, erase it from the map, insert the new node at the front.

### LFU

Three pieces of state:

- `keyMap`: `key → Node*`
- `freqList`: `frequency → doubly linked list` (most recent at the front of each list)
- `minFreq`: the smallest frequency that has a non-empty list

Using a key moves its node from bucket *f* to bucket *f + 1*. If bucket *f* becomes empty it is removed, and if `f == minFreq` then `minFreq` becomes *f + 1*. To evict, take the **last** node of `freqList[minFreq]`: the lowest frequency, and the least recently used among ties. A new key always enters at frequency 1 and resets `minFreq` to 1.

### Simulation

For each request the simulator calls `get`, and on a miss it calls `put`. Each request produces a step:

```json
{ "index": 5, "request": "D", "hit": false, "evicted": "B", "cache": ["D", "A", "C"] }
```

Statistics are added up from the steps: total requests, hits, misses, evictions, and `hitRatio = hits / total × 100`. A common `Cache` interface means the simulator never knows which policy it is driving, so adding a third policy means implementing the interface and adding one line to the factory.

The cache is displayed in a policy-specific order: LRU most recent first; LFU highest frequency first, ties by recency. In both, the next eviction candidate is on the right.

## API

`POST /api/simulate`

```json
{ "policy": "LRU", "capacity": 2, "requests": "A B A" }
```

- `policy`: `"LRU"`, `"LFU"` or `"BOTH"` (case-insensitive)
- `capacity`: integer, 1 to 1000
- `requests`: a space-separated string or a list of strings (at most 5000 requests, each at most 32 characters)

The response has one entry in `results` per policy (`"BOTH"` returns LRU, then LFU):

```json
{
  "results": [
    {
      "policy": "LRU",
      "capacity": 2,
      "steps": [
        { "index": 1, "request": "A", "hit": false, "evicted": null, "cache": ["A"] },
        { "index": 2, "request": "B", "hit": false, "evicted": null, "cache": ["B", "A"] },
        { "index": 3, "request": "A", "hit": true, "evicted": null, "cache": ["A", "B"] }
      ],
      "stats": { "totalRequests": 3, "hits": 1, "misses": 2, "evictions": 0, "hitRatio": 33.33 }
    }
  ]
}
```

Errors return `{ "error": "..." }` with status 400 for bad input, 413 if the request body is larger than 512 KB, and 500 if the C++ engine is missing or fails. `GET /api/health` returns `{ "status": "ok" }`.

## Complexity

| Operation | LRU | LFU |
|---|---|---|
| `get` | O(1) average | O(1) average |
| `put` | O(1) average | O(1) average |
| Eviction | O(1) | O(1) |
| Space | O(C) | O(C) |

"Average" because of the hash maps; C is the capacity. Producing the cache contents for display (`keys()`) costs O(C) per step (LFU also sorts its frequency buckets). That is a cost of the visualization, not of the cache operations.

## Testing

```bash
make test                  # C++, backend and frontend logic tests
cd frontend && npm test    # also runs the React component tests
```

- **C++** (`cpp/tests`): the linked list; LRU and LFU edge cases (capacity 0 and 1, empty cache, repeated access, existing keys, tie-breaks, `minFreq`); LFU checked against a brute-force reference model on randomized workloads; the common interface; simulator results compared with hand-computed expectations. Build with `-fsanitize=address,undefined` to run them under sanitizers.
- **Backend** (`backend/test_api.py`): valid requests against the real C++ program, invalid policy / capacity / empty stream, size limits, special characters, missing engine, static file serving (including path traversal).
- **Frontend**: step-through logic (`src/logic.test.js`) and React component tests (`src/App.ui.test.jsx`, Vitest + Testing Library): run, step, statistics, LRU/LFU switch, compare mode, error display.
- **CI** (`.github/workflows/ci.yml`): all of the above on every push, plus a job that builds the Docker image and smoke-tests the running container.

## Future improvements

- Show how many times each key has been used in the LFU view
- Larger generated workloads (Zipf, sequential scan) and a chart of hit ratio against capacity
- More policies (FIFO, MRU) through the existing `Cache` interface
- Call the engine directly (pybind11) instead of through a subprocess
