# AI Fitness Coach v1 — Release Notes

## What's Included

v1 is a **functional MVP** for self-hosted AI fitness and nutrition coaching. It demonstrates the core orchestration pattern of using LLMs for planning while relying on deterministic code for safety and external systems as sources of truth.

### Core Capabilities
- Goal-based workout and meal plan generation (fat loss, muscle gain, maintenance)
- Adaptive replanning based on weight trends and adherence
- Full audit trail for all coach adjustments
- 4-week analytics dashboard with goal alignment tracking
- GDPR-compliant data export/import

## Known Limitations

### v1 Scope Boundaries

| Area | Limitation | Future Consideration |
|------|------------|---------------------|
| **Authentication** | No user auth - localStorage user ID only | Add OAuth/JWT in v2 |
| **Multi-User** | Single-user mode - no user switching UI | Add user management in v2 |
| **Offline** | Basic service worker - no offline data sync | IndexedDB caching in v2 |
| **HealthKit** | Weight sync metadata only - no actual HealthKit | Native iOS/Android in v2 |
| **Exercise Database** | Depends on wger connectivity | Add local exercise cache |
| **Recipe Database** | Depends on Tandoor connectivity | Add local recipe cache |

### Technical Limitations

1. **LLM Dependency** — Plan generation requires working LLM connection (Ollama/OpenAI/Anthropic)
2. **SQLite** — Single-file database; not suitable for high-concurrency production
3. **No Rate Limiting** — API endpoints are not rate-limited
4. **No Email/Notifications** — No notification system for reminders or alerts
5. **No Biometric Sync** — Weight entries are manual or seeded; no real device sync

### Frontend Limitations

1. **No Dark/Light Toggle** — Dark mode only (by design for v1)
2. **No Exercise Logging UI** — Workout completion is binary (complete button only)
3. **No Meal Logging UI** — Nutrition tracking is adherence-based, not calorie-counting
4. **Limited Accessibility** — Basic ARIA labels only; needs audit for screen readers

### Data Limitations

1. **No Historical Plans** — Only current week's plan is displayed
2. **4-Week Trend Window** — Analytics limited to last 4 weeks
3. **No Goal History** — Goal changes aren't tracked over time
4. **No Photo Progress** — No body progress photo tracking

## Production Checklist

Before deploying to production:

- [ ] Add proper authentication (OAuth, JWT, or similar)
- [ ] Replace SQLite with PostgreSQL for concurrency
- [ ] Add rate limiting on API endpoints
- [ ] Configure proper CORS for production domain
- [ ] Set secure cookie settings
- [ ] Add health check monitoring
- [ ] Configure backup strategy for database
- [ ] Review and harden security headers
- [ ] Add error reporting (Sentry, etc.)
- [ ] Set up log aggregation

## Upgrade Path

When upgrading from v1:

1. **Export user data** before upgrading using `/api/admin/export/{user_id}`
2. **Database migrations** — Run any new Alembic migrations
3. **Re-import data** if schema changes using `/api/admin/import/restore`
4. **Test with demo data** before restoring real user data

## Feedback

For bugs, feature requests, or questions:
- Open an issue on the project repository
- Include version number, browser/device info, and steps to reproduce
