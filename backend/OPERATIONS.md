# AI Fitness Coach v1 - Operational Guide

This document covers operational procedures for running, debugging, and maintaining the AI Fitness Coach backend.

## Table of Contents

1. [Quick Start](#quick-start)
2. [API Endpoints Reference](#api-endpoints-reference)
3. [Demo Data Setup](#demo-data-setup)
4. [Audit Bundle Export](#audit-bundle-export)
5. [Weight Sync & Biometric Integration](#weight-sync--biometric-integration)
6. [Plan Revision System](#plan-revision-system)
7. [Weekly Review & Coach Insights](#weekly-review--coach-insights)
8. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Running the Server

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### Running Tests

```bash
cd backend
python -m pytest tests/ -v
```

### Environment Variables

```bash
# Required
DATABASE_URL=sqlite+aiosqlite:///./fitness_coach.db

# Optional - External Providers
WGER_BASE_URL=https://wger.de/api/v2
WGER_API_TOKEN=your_token
TANDOOR_BASE_URL=https://your-tandoor.com
TANDOOR_API_TOKEN=your_token

# Optional - LLM
OPENAI_API_KEY=your_key
ANTHROPIC_API_KEY=your_key
```

---

## API Endpoints Reference

### Dashboard & Daily Views

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/dashboard/{user_id}` | GET | Main dashboard with today's workout, meals, and progress |
| `/api/workouts/today/{user_id}` | GET | Today's workout with rest day detection |
| `/api/meals/today/{user_id}` | GET | Today's meals with nutrition targets |

### Weekly Review & Analytics

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/review/weekly/{user_id}` | GET | Aggregated weekly analytics and coach insights |
| `/api/review/trends/{user_id}` | GET | 4-week trend cards and goal alignment status |

### Profile Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/profile/` | POST | Create user profile |
| `/api/profile/{user_id}` | GET | Get profile |
| `/api/profile/{user_id}` | PUT | Update profile |
| `/api/profile/{user_id}` | DELETE | Delete profile |

### Weight Tracking

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/profile/weight` | POST | Log manual weight entry |
| `/api/profile/weight/sync` | POST | Sync from external source (HealthKit/Google Fit) |
| `/api/profile/weight/latest/{user_id}` | GET | Get latest weight with trend |
| `/api/profile/weight/history/{user_id}` | GET | Get weight history and revisions |

### Planning

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/planning/weekly` | POST | Generate new weekly plan |
| `/api/planning/current/{user_id}` | GET | Get active plan |
| `/api/planning/replan` | POST | Trigger adaptive replanning |
| `/api/planning/replan/approve/{revision_id}` | POST | Approve pending revision |
| `/api/planning/replan/undo/{revision_id}` | POST | Undo applied revision |
| `/api/planning/revisions/{plan_id}` | GET | Get all revisions for a plan |

### Admin Operations

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/admin/seed/demo` | POST | Seed demo data |
| `/api/admin/seed/demo/status` | GET | Check demo data status |
| `/api/admin/seed/demo` | DELETE | Clear demo data |
| `/api/admin/export/{user_id}` | GET | Export audit bundle |
| `/api/admin/export/{user_id}/summary` | GET | Check export summary |
| `/api/admin/import/preview` | POST | Preview import from audit bundle |
| `/api/admin/import/restore` | POST | Restore from audit bundle |

---

## Demo Data Setup

The demo data service creates a complete test user with realistic data.

### Seeding Demo Data

```bash
# Via API
curl -X POST "http://localhost:8000/api/admin/seed/demo"

# With custom user ID
curl -X POST "http://localhost:8000/api/admin/seed/demo?user_id=my-test-user"

# Reset existing data
curl -X POST "http://localhost:8000/api/admin/seed/demo?clear_existing=true"
```

### What Gets Created

- **User Account**: `demo-user-001`
- **Profile**: Fat loss goal, 4 days/week, full equipment
- **Weight History**: 14 days with realistic fluctuation, mixed sources (manual + HealthKit)
- **Weekly Plan**: 4-day upper/lower split with meal plans
- **Revisions**: 3 sample revisions (superseded, applied, reverted)

### Checking Demo Status

```bash
curl "http://localhost:8000/api/admin/seed/demo/status"
```

Response:
```json
{
  "user_id": "demo-user-001",
  "has_profile": true,
  "profile_goal": "fat_loss",
  "weight_entries": 15,
  "has_active_plan": true,
  "plan_id": "plan-demo-user-001-20240115",
  "revision_count": 3
}
```

---

## Audit Bundle Export

Export all user data for debugging, compliance (GDPR), or backup.

### Full Export

```bash
curl "http://localhost:8000/api/admin/export/{user_id}" > audit-bundle.json
```

### Selective Export

```bash
# Exclude plans and workout logs
curl "http://localhost:8000/api/admin/export/{user_id}?include_plans=false&include_workout_logs=false"
```

### Export Summary

Check what would be exported before downloading:

```bash
curl "http://localhost:8000/api/admin/export/{user_id}/summary"
```

Response:
```json
{
  "user_id": "demo-user-001",
  "counts": {
    "user_exists": true,
    "profile_exists": true,
    "weight_entries": 15,
    "plans": 1,
    "revisions": 3,
    "workout_logs": 0,
    "adherence_records": 0
  },
  "total_records": 19,
  "has_data": true
}
```

### Bundle Structure

```json
{
  "metadata": {
    "user_id": "demo-user-001",
    "exported_at": "2024-01-15T10:30:00",
    "version": "1.0",
    "record_counts": { ... }
  },
  "user": { ... },
  "profile": { ... },
  "weight_entries": [ ... ],
  "plans": [ ... ],
  "revisions": [ ... ],
  "workout_logs": [ ... ],
  "adherence_records": [ ... ]
}
```

---

## Audit Bundle Import/Restore

Restore user data from an exported audit bundle.

### Preview Import

Before restoring, preview what will happen:

```bash
curl -X POST "http://localhost:8000/api/admin/import/preview" \
  -H "Content-Type: application/json" \
  -d '{"bundle": <audit-bundle-json>}'
```

Response:
```json
{
  "valid": true,
  "bundle_version": "1.0",
  "source_user_id": "demo-user-001",
  "target_user_id": "demo-user-001",
  "preview": {
    "user": {"action": "create", "exists": false},
    "profile": {"action": "create", "exists": false},
    "weight_entries": {"count": 15, "new": 15, "existing": 0},
    "plans": {"count": 1, "new": 1, "existing": 0}
  },
  "conflicts": [],
  "warnings": []
}
```

### Restore Data

Execute the restore with a mode:

```bash
# Replace mode - delete existing, restore from bundle (creates backup)
curl -X POST "http://localhost:8000/api/admin/import/restore" \
  -H "Content-Type: application/json" \
  -d '{"bundle": <audit-bundle-json>, "mode": "replace"}'

# Merge mode - add new records only, skip existing
curl -X POST "http://localhost:8000/api/admin/import/restore" \
  -H "Content-Type: application/json" \
  -d '{"bundle": <audit-bundle-json>, "mode": "merge"}'

# Dry run - validate without committing
curl -X POST "http://localhost:8000/api/admin/import/restore" \
  -H "Content-Type: application/json" \
  -d '{"bundle": <audit-bundle-json>, "mode": "replace", "dry_run": true}'
```

### Restore Modes

| Mode | Behavior |
|------|----------|
| `replace` | Delete all existing data, restore from bundle (backup created first) |
| `merge` | Add new records only, skip existing (by ID), never delete |

### Restore to Different User

Override the target user ID:

```bash
curl -X POST "http://localhost:8000/api/admin/import/restore" \
  -H "Content-Type: application/json" \
  -d '{"bundle": <audit-bundle-json>, "mode": "replace", "target_user_id": "new-user-id"}'
```

### Backup Location

When using `replace` mode, a backup is automatically created in `backups/` directory with format:
`backup-YYYYMMDD-HHMMSS-{user_id}.json`

---

## Weight Sync & Biometric Integration

### Sync Flow

1. Mobile app receives weight from HealthKit/Google Fit
2. App calls `/api/profile/weight/sync` with source metadata
3. Service deduplicates entries (exact match + near-duplicate detection)
4. Evaluates if replan threshold is met
5. Triggers replan if conditions are satisfied

### Sync Request

```bash
curl -X POST "http://localhost:8000/api/profile/weight/sync" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "demo-user-001",
    "weight_kg": 83.5,
    "source": "healthkit",
    "source_id": "HK-12345",
    "measured_at": "2024-01-15T08:00:00Z"
  }'
```

### Deduplication Rules

| Type | Detection Method | Result |
|------|------------------|--------|
| Exact Duplicate | Same `source_id` | Ignored |
| Near Duplicate | Same source + within 5 min + ±0.1kg | Ignored |
| Different Source | Different source | Creates new entry |
| Manual vs Sync | Manual is separate | Both coexist |

### Replan Triggers

Replanning is triggered when:

1. Weight change exceeds threshold (default: 0.5kg)
2. Cooldown period has passed (default: 3 days since last revision)
3. Active plan exists

### Per-User Sensitivity Settings

Users can customize replan sensitivity in their profile:

```json
{
  "replan_weight_threshold_kg": 0.5,
  "replan_missed_workout_threshold": 2,
  "replan_cooldown_days": 3
}
```

---

## Plan Revision System

### Revision States

| State | Description | Can Transition To |
|-------|-------------|-------------------|
| `pending` | Awaiting user approval | `approved`, `superseded`, `blocked` |
| `applied` | Auto-applied by system | `reverted`, `superseded` |
| `approved` | User approved | `reverted`, `superseded` |
| `reverted` | User undid revision | Terminal |
| `superseded` | Replaced by newer revision | Terminal |
| `blocked` | Blocked by newer plan | Terminal |

### Target Areas

- `workout` - Affects workout volume/intensity
- `nutrition` - Affects calorie/macro targets
- `both` - Affects both areas

### Supersession Rules

When a new revision is created:
1. All active revisions for the same target area are marked `superseded`
2. A revision targeting `both` supersedes all active revisions
3. Workout revisions don't affect nutrition revisions (independent states)

### Impact Summary

API responses include an `impact_summary` field showing active adjustments:

```json
{
  "impact_summary": "This week's active adjustments: calories -150, volume -10%"
}
```

### Reverting a Revision

```bash
curl -X POST "http://localhost:8000/api/planning/replan/undo/{revision_id}"
```

This creates a compensating revision (inverse patch) and marks the original as `reverted`.

---

## Weekly Review & Coach Insights

The weekly review endpoint aggregates analytics to help users understand their progress.

### Getting a Weekly Review

```bash
curl "http://localhost:8000/api/review/weekly/{user_id}"
```

### Response Structure

```json
{
  "week_start": "2024-01-15",
  "week_end": "2024-01-21",
  "goal": "fat_loss",

  "weight": {
    "start_kg": 85.2,
    "current_kg": 84.6,
    "change_kg": -0.6,
    "trend": "losing",
    "aligned_with_goal": true
  },

  "workouts": {
    "planned": 4,
    "completed": 3,
    "completion_pct": 75.0,
    "avg_energy": 3.5,
    "total_duration_min": 165
  },

  "nutrition": {
    "days_on_target": 5,
    "total_days": 7,
    "adherence_pct": 71.4,
    "avg_calories": 1850,
    "target_calories": 2000
  },

  "coach_adjustments": [
    {
      "trigger": "weight_change",
      "area": "nutrition",
      "change": "calories -150",
      "status": "applied",
      "date": "2024-01-17"
    }
  ],

  "insights": [
    "Weight trending down (-0.6 kg) - on track for fat loss",
    "3/4 workouts completed - great consistency",
    "Nutrition adherence at 71% - consider meal prep"
  ],

  "next_action": "Complete today's lower body workout to stay on track"
}
```

### Week Offset

View previous weeks using the `week_offset` parameter:

```bash
# Last week
curl "http://localhost:8000/api/review/weekly/{user_id}?week_offset=-1"

# Two weeks ago
curl "http://localhost:8000/api/review/weekly/{user_id}?week_offset=-2"
```

### Insight Generation Rules

Insights are generated based on:

| Metric | Positive | Warning |
|--------|----------|---------|
| Weight trend | Aligned with goal | Not aligned with goal |
| Workouts | ≥75% completion | <50% completion |
| Energy | ≥4.0 average | <2.5 average |
| Nutrition | ≥80% adherence | <60% adherence |

### Empty States

The endpoint handles missing data gracefully:
- No profile → Prompts to complete profile
- No plan → Prompts to generate a plan
- No workout logs → Shows 0/planned
- No weight entries → Omits weight section

### 4-Week Trends Dashboard

Get aggregated trends for dashboard cards:

```bash
curl "http://localhost:8000/api/review/trends/{user_id}"
```

Response includes:

```json
{
  "trends": {
    "weight": {
      "weeks": [...],
      "total_change_kg": -0.8,
      "direction": "down"
    },
    "workouts": {
      "weeks": [...],
      "avg_completion_pct": 75.0,
      "direction": "stable"
    },
    "nutrition": {
      "weeks": [...],
      "avg_adherence_pct": 73.8,
      "direction": "up"
    }
  },
  "revision_frequency": {
    "total": 5,
    "auto_applied": 3,
    "assessment": "moderate"
  },
  "goal_alignment": {
    "status": "on_track"
  }
}
```

**Revision Frequency Assessment**:
| Total | Assessment |
|-------|------------|
| 0-1 | stable |
| 2-4 | moderate |
| 5+ | active |

**Goal Alignment Status**:
| Aligned Metrics | Status |
|-----------------|--------|
| ≥70% | on_track |
| 40-69% | mixed |
| <40% | off_track |

---

## Troubleshooting

### Common Issues

#### "No active plan" on Dashboard

**Cause**: User has profile but no generated plan.

**Solution**: Generate a plan via `/api/planning/weekly`.

#### Weight sync not triggering replan

**Possible causes**:
1. Weight change below threshold
2. Cooldown period active
3. No active plan exists

**Debug**:
```bash
# Check latest weight and trend
curl "http://localhost:8000/api/profile/weight/latest/{user_id}"

# Check revision history
curl "http://localhost:8000/api/planning/revisions/user/{user_id}"
```

#### Revision stuck in "pending" state

**Cause**: User hasn't approved the revision.

**Solution**: Either approve via API or let system supersede on next trigger.

### Debug Queries

```python
# Check effective state query (in console/debugger)
SELECT * FROM plan_revisions
WHERE plan_id = ? AND status IN ('applied', 'approved', 'pending')
ORDER BY created_at DESC
LIMIT 1;
```

### Log Analysis

The backend uses structured logging with correlation IDs:

```
2024-01-15 10:30:00 | INFO | weight_sync | weight_synced user_id=demo-user-001 status=created
2024-01-15 10:30:01 | INFO | planning_api | replan_triggered user_id=demo-user-001 trigger=weight_change
```

Key log events:
- `weight_synced` - Weight sync processed
- `replan_triggered` - Replan evaluation positive
- `revisions_superseded` - Active revisions superseded

---

## Health Check

```bash
curl "http://localhost:8000/api/health"
```

Response:
```json
{
  "status": "healthy",
  "service": "AI Fitness Coach v1",
  "timestamp": "2024-01-15T10:30:00"
}
```
