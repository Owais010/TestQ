# TestQ — Independent AI QA Agent

> **"Let AI build it. Let independent AI try to break it."**

TestQ is an AI-powered QA testing platform that takes a GitHub repository, safely executes the application in an isolated Docker sandbox, generates adversarial tests, collects real evidence, and produces actionable bug reports.

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+ (for frontend, Phase 8)
- Docker Desktop (running)
- Git

### Backend Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # macOS/Linux

pip install -r requirements.txt
```

### Environment Configuration

```bash
# Copy the template
cp .env.example .env

# Edit .env if needed (defaults work for local development)
```

### Build Sandbox Images

```bash
# Build the Node.js sandbox image
docker build -f sandbox/Dockerfile.node -t testq-sandbox-node:latest sandbox/

# Build the Python sandbox image
docker build -f sandbox/Dockerfile.python -t testq-sandbox-python:latest sandbox/
```

### Start the Backend

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs available at: http://localhost:8000/docs

### Run Tests

```bash
cd backend
pytest tests/ -v
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system design.

## V1 Constraints

- **100% local/free** — no paid APIs or cloud infrastructure required
- **AI Provider:** Ollama (local) is the default; OpenAI is optional
- **Database:** SQLite (local file)
- **Execution:** Docker containers on the local machine
- **Supported Technologies:** Next.js, React/Vite, Node.js, Python/FastAPI

## Supported Technologies (V1)

| Technology   | Detection Signals                        |
| ------------ | ---------------------------------------- |
| Next.js      | `next` in package.json, `next.config.*`  |
| React + Vite | `vite` + `react` in deps, `vite.config.*`|
| Node.js      | `package.json` with `start` script       |
| FastAPI      | `fastapi` in requirements.txt/pyproject  |

Unsupported technologies (Java, Rust, Go, Ruby, etc.) are detected and rejected honestly.

## API Endpoints

| Endpoint                       | Method | Description              |
| ------------------------------ | ------ | ------------------------ |
| `/health`                      | GET    | Backend health check     |
| `/api/projects`                | POST   | Create project           |
| `/api/projects/{id}`           | GET    | Get project details      |
| `/api/test-runs`               | POST   | Start a new test run     |
| `/api/test-runs/{id}`          | GET    | Get run status/progress  |
| `/api/test-runs/{id}/cancel`   | POST   | Cancel active run        |
| `/api/test-runs/{id}/logs`     | GET    | Get run logs             |

## Security

- Repository code **never** executes on the TestQ host
- Every test run uses a **disposable Docker container**
- Containers have CPU, memory, and PID limits
- No `--privileged` mode, no Docker socket exposure
- Automatic cleanup after every run

## Current Phase

Phase 1 — Execution Foundation (GitHub → Clone → Detect → Docker → Build → Start → Health Check)

## License

Proprietary — All rights reserved.
