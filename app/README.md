# Loopy desktop app

A thin Electron shell around the `ninexf app` server. The whole UI lives in the
Python package ([ninexf/webapp.py](../ninexf/webapp.py)) and works in any
browser — this wrapper adds a native dark window and a native folder picker.

## Run it

Requires Node.js and a Python with `ninexf` importable:

```bash
# once, from the repo root
pip install -e .

# then
cd app
npm install
npm start
```

The app spawns `python3 -m ninexf app --no-browser`, waits for it, and opens
the window. If you already have `ninexf app` running (from the CLI), it reuses it.

Environment overrides: `NINEXF_PYTHON` (python executable), `NINEXF_PORT`
(default 9118).

## macOS release builds

The first publishable path is macOS-first:

```bash
cd app
npm install
npm run dist:mac
```

That emits release artifacts under [app/dist](/Users/manaskandimalla/Desktop/2026-Projects/Loops-Experimentation/app/dist).

## No Node? No problem

The identical UI without Electron:

```bash
python3 -m ninexf app
```

opens the same chat interface in your default browser.
