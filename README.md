# AI Fitness Coach v1

**Self-hosted AI fitness and nutrition coach** built as an orchestration layer over proven systems.

> **Core Philosophy**: LLM = planner + reasoning. Deterministic code = guardrails. External systems = source of truth.

## Architecture

```
PWA Frontend (vanilla JS)
        |
Orchestration API (FastAPI + JWT auth)
        |
 +------+-------+-------+
 |      |       |       |
wger  Tandoor  Ollama  PostgreSQL
```

## Deployment (Proxmox LXC)

The recommended deployment is a Docker container inside a Proxmox LXC.

### 1. Create the LXC and install

From your **Proxmox host** shell:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/rcmiller01/Workout_Coach_v2/main/scripts/install.sh)"
```

Or with custom options:

```bash
bash scripts/install.sh --id 200 --hostname coach --ip 192.168.50.100 --memory 2048 --cores 2
```

This creates a Debian 12 LXC with Docker, clones the repo to `/opt/ai-fitness-coach`, generates a secure `SECRET_KEY`, and sets the app to production mode.

### 2. Configure environment variables

The `.env` file is created at `/opt/ai-fitness-coach/.env` from the example template. Edit it with your network settings:

```bash
# Enter the container (replace 200 with your CT ID)
pct enter 200

# Edit the environment file
nano /opt/ai-fitness-coach/.env
```

Required settings to update:

```env
# Database — your PostgreSQL instance
DATABASE_URL=postgresql+asyncpg://postgres:yourpassword@192.168.50.137:5432/fitness_coach

# wger — workout/exercise database
WGER_BASE_URL=http://192.168.50.98:3000/api/v2
WGER_API_TOKEN=your-wger-token

# Tandoor — recipe database
TANDOOR_BASE_URL=http://192.168.50.226:8002/api
TANDOOR_API_TOKEN=your-tandoor-token

# Ollama — LLM for plan generation
LLM_PROVIDER=ollama
LLM_MODEL=qwen3:14b
LLM_BASE_URL=http://192.168.50.219:11434

# CORS — your app's URL (or * for local network)
CORS_ORIGINS=*
```

Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X` in nano).

### 3. Start the app

```bash
cd /opt/ai-fitness-coach
docker compose up -d
```

The app will be available at `http://<container-ip>:8000`.

### 4. Verify

```bash
curl http://localhost:8000/api/dashboard/health
# {"status":"healthy","service":"AI Fitness Coach v1",...}
```

### Updating

```bash
bash /opt/ai-fitness-coach/scripts/update.sh
```

This pulls the latest code, rebuilds the Docker image, and restarts the app.

## Local Development

```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows (or source venv/bin/activate on Linux/Mac)
pip install -r requirements.txt

# Copy and edit environment config
cp ../.env.example ../.env

# Start the API
uvicorn app.main:app --reload --port 8000
```

## External Services Setup

| Service | Purpose | Setup |
|---------|---------|-------|
| **PostgreSQL** | Database | Create a database, set `DATABASE_URL` in `.env` |
| **wger** | Workout/exercise DB | Generate API token in wger settings |
| **Tandoor** | Recipe DB | Generate API token in Tandoor settings (uses Bearer auth) |
| **Ollama** | LLM plan generation | `ollama pull qwen3:14b` on your GPU machine |

## API Endpoints

All endpoints require JWT authentication (except `/api/auth/*` and `/api/dashboard/health`).

### Auth
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/auth/register` | Create account |
| `POST` | `/api/auth/login` | Login (returns JWT) |
| `POST` | `/api/auth/refresh` | Refresh access token |
| `GET` | `/api/auth/me` | Current user info |

### Core
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/dashboard/dashboard` | Today's dashboard |
| `POST` | `/api/planning/weekly` | Generate weekly plan (rate limited: 3/hr) |
| `GET` | `/api/planning/current` | Current active plan |
| `POST` | `/api/planning/replan` | Trigger adaptive replan (rate limited: 10/hr) |
| `GET` | `/api/workouts/today` | Today's workout |
| `POST` | `/api/workouts/log` | Log completed workout |
| `GET` | `/api/meals/today` | Today's meals |
| `POST` | `/api/meals/log` | Log a meal |
| `POST` | `/api/profile/steps` | Log daily step count |

## Tech Stack

- **Backend**: Python 3.11, FastAPI, SQLAlchemy 2.0, PostgreSQL
- **Auth**: JWT (python-jose + passlib/bcrypt)
- **LLM**: LiteLLM (Ollama, OpenAI, Anthropic)
- **Rate Limiting**: slowapi
- **Frontend**: Vanilla JS PWA with glassmorphism dark theme
- **Deploy**: Docker + Proxmox LXC helper script

## License

MIT
