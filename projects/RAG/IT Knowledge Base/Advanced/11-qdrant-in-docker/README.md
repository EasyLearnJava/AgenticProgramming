# 11 · Qdrant in Docker (Advanced)

> **Status:** 📝 Planned: this README is the plan; there's no code yet.
> **Production version of:** [Basic · 11 · Qdrant on Disk](../../Basic/11-qdrant-on-disk/README.md)

The basic version keeps the chunks on disk with Qdrant's local mode, so they're kept between runs and embedded only
once. This version runs the whole app the way it would run on a server: the app in its own container, Qdrant as a
secured and backed-up server, secrets kept out of images and code, health checks for both, and a pipeline that tests
and builds every change.

---

## 🎯 What This Project Will Do

- **Put the app in a container** of its own, small and running as a non-root user
- **Run app and Qdrant together** with Compose: health checks, restart rules, resource limits, a persistent volume
- **Secure Qdrant**: an API key, no port open to the outside, and TLS where it crosses a network
- **Keep secrets out**: keys come from the environment or a secrets store, never from the image or the repo
- **Back up and restore**: Qdrant snapshots on a schedule, and a tested restore
- **Build every change in CI**: tests, image build, and a vulnerability scan

---

## 🗺️ Roadmap

| # | Concept | What it adds | Why it matters in production |
|---|---|---|---|
| 1 | **App container** | A multi-stage Dockerfile with pinned versions, a non-root user and a `.dockerignore` | The same image runs everywhere, small and with less to attack |
| 2 | **Compose for both** | App and Qdrant services, `depends_on` with health checks, restart policies, limits and a named volume | Start-up order is right, and a crash restarts on its own |
| 3 | **Qdrant security** | An API key on Qdrant, its port reachable only from the app's network, TLS when it's remote | The knowledge base can't be read or wiped by anyone who finds the port |
| 4 | **Secrets management** | The Gemini key and Qdrant key from environment variables or a secrets store, checked at start-up | Keys never end up in an image layer, a log or git |
| 5 | **Snapshots and restore** | A scheduled snapshot of the collection, kept off the machine, and a restore drill | A lost disk costs minutes, not a full re-ingestion |
| 6 | **Zero-downtime re-index** | The alias switch from 05, run as a job against the live stack | A new model or chunking rolls out without the app going down |
| 7 | **CI pipeline** | On every push: tests, lint, image build, a vulnerability scan, and an image tagged with the commit | A broken change is stopped before it's deployed |
| 8 | **A deployment target** | The image deployed to one managed service (such as Cloud Run), with the settings and secrets it needs | A path from a laptop to a real URL |

---

## 🏗️ Planned Architecture

```text
            ┌──────────────────────── private network ────────────────────────┐
user ──→ app container (non-root, health check) ──→ Qdrant (API key, volume, health check)
            │                │                                   │
            │                └──→ Gemini (key from secrets)      └──→ snapshots ──→ off-machine storage
            └──────────────────────────────────────────────────────────────────┘

git push ──→ CI: tests · lint · build image · scan ──→ registry (tagged with the commit) ──→ deploy
```

---

## ✅ Done When

- `docker compose up` starts both services healthy, and stopping Qdrant marks the app "not ready" until it's back
- The image runs as non-root, holds no key, and passes the scan with no critical findings
- A snapshot can be restored into an empty Qdrant, and the app answers from it
- CI runs on every push and blocks a change whose tests fail

---

## 📚 Next Steps

**[12 · Tuning (Advanced)](../12-tuning/README.md)**: an evaluation suite, experiment tracking, and a quality gate
in CI.
