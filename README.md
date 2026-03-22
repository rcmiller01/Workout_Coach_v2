# 🏋️ AI Fitness Coach v1

**Self-hosted AI fitness and nutrition coach** built as an orchestration layer over proven systems.

> **Core Philosophy**: LLM = planner + reasoning. Deterministic code = guardrails. External systems = source of truth.

## Architecture

```
Mobile App / PWA
        ↓
Orchestration API (FastAPI)
        ↓
 ┌───────────────┬───────────────┐
 │               │               │
wger API     Tandoor API     LLM (Ollama)
(workouts)   (recipes)       (planning)
```

## Quick Start

### 1. Clone & Configure

```bash
cp .env.example .env
# Edit .env with your settings
```

### 2. Start with Docker Compose

```bash
docker-compose up -d
```

This starts:
- **Coach API** → `http://localhost:8000` (+ Swagger docs at `/docs`)
- **wger** → `http://localhost:8001`
- **Tandoor Recipes** → `http://localhost:8002`

### 3. Local Development (without Docker)

```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt

# Start the API
uvicorn app.main:app --reload --port 8000
```

### 4. Setup External Systems

1. **wger**: Visit `http://localhost:8001`, create account, generate API token in settings
2. **Tandoor**: Visit `http://localhost:8002`, create account, generate API token
3. **Update `.env`** with your tokens

### 5. (Optional) Start Ollama for LLM

```bash
ollama serve
ollama pull llama3
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/profile/` | Create user profile |
| `GET` | `/api/profile/{user_id}` | Get profile |
| `PUT` | `/api/profile/{user_id}` | Update profile |
| `GET` | `/api/dashboard/{user_id}` | Today's dashboard |
| `POST` | `/api/planning/weekly` | Generate weekly plan |
| `GET` | `/api/planning/current/{user_id}` | Current active plan |
| `GET` | `/api/workouts/today/{user_id}` | Today's workout |
| `POST` | `/api/workouts/log` | Log workout |
| `GET` | `/api/meals/today/{user_id}` | Today's meals |
| `POST` | `/api/meals/import-recipe` | Import recipe from URL |

## Core Components

- **Orchestration API** — FastAPI backend that coordinates everything
- **Provider Adapters** — wger (workouts) + Tandoor (recipes) integrations
- **LLM Planner** — Generates personalized workout & meal plans
- **Rules Engine** — Validates plans against safety constraints
- **Sync Engine** — Keeps external systems in sync
- **Substitution Engine** — Exercise & recipe alternatives

## Tech Stack

- **Backend**: Python 3.11, FastAPI, SQLAlchemy 2.0, SQLite
- **LLM**: Ollama (local) or OpenAI/Anthropic via litellm
- **HTTP Client**: httpx (async)
- **Frontend**: PWA (Progressive Web App)
- **Infrastructure**: Docker Compose

## License

MIT
