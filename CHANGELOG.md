# Changelog

All notable changes to AI Fitness Coach are documented here.

## [1.0.0] - 2026-03-21

### Added

#### Core Features
- **User Profiles** — Create and manage fitness profiles with goals, training days, and macro targets
- **Weekly Plan Generation** — AI-powered workout and meal plan generation based on user goals
- **Workout Tracking** — Log workout completion with exercise details and energy levels
- **Nutrition Tracking** — Daily meal plans with macro breakdowns and shopping lists
- **Weight Logging** — Track body weight over time with source metadata (manual, HealthKit sync)

#### Adaptive Coaching
- **Adaptive Replanning** — Automatic plan adjustments based on weight trends and workout adherence
- **Revision Lifecycle** — Full audit trail for all plan changes (pending, applied, approved, reverted, superseded, blocked)
- **User Approval Flow** — Pending revisions require user approval for significant changes
- **Auto-Apply for Small Changes** — Minor adjustments (<=100 kcal, <=10% volume) auto-apply with undo option
- **Cooldown Protection** — Prevents over-adjustment by respecting cooldown periods between revisions

#### Analytics & Insights
- **4-Week Trends Dashboard** — Weight, workout, and nutrition trends with direction indicators
- **Goal Alignment Tracking** — Visual indicator showing progress toward fitness goal
- **Coach Activity Summary** — Track total adjustments, auto-applied, user-approved, and undone revisions
- **Weekly Review** — Detailed weekly breakdown with insights and next-action recommendations

#### Administration
- **Demo Data Seeding** — Quick setup with realistic demo data for testing
- **Audit Bundle Export** — GDPR-compliant full user data export
- **Audit Bundle Import** — Restore user data from exported bundles (merge/replace modes)
- **Dry-Run Support** — Preview import operations before committing

#### Frontend (PWA)
- **Mobile-First Design** — Responsive glassmorphism UI optimized for mobile
- **Bottom Navigation** — Quick access to Today, Workout, Meals, Shop, Progress, Insights
- **Offline Support** — Service worker for basic offline functionality
- **SVG Charts** — Custom weight trend and progress visualizations (no external dependencies)

### Technical
- FastAPI with async SQLAlchemy 2.0 (aiosqlite)
- Pydantic response models for type-safe API
- LiteLLM for model-agnostic LLM integration
- 81 passing tests (unit + integration)
- QA checklist with 100+ test scenarios

---

## [0.1.0] - Initial Development

- Project scaffolding
- Basic profile and planning endpoints
- Provider adapters for wger and Tandoor
