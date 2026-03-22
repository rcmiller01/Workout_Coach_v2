# AI Fitness Coach v1 — QA Checklist

> Pre-release validation checklist for v1 milestone

---

## 1. User Onboarding Flow

### 1.1 Profile Setup
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| 1.1.1 | New user sees setup modal | Clear localStorage, load app | Setup modal displays |
| 1.1.2 | Valid profile creation | Fill form with valid data, submit | Profile created, modal closes, dashboard loads |
| 1.1.3 | Missing required fields | Submit form with empty goal | Error message shown |
| 1.1.4 | Profile persists | Create profile, refresh page | User remains logged in |
| 1.1.5 | Profile stored in localStorage | Complete setup | `coach_user_id` key exists |

### 1.2 Time-Based Greeting
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| 1.2.1 | Morning greeting | Load app before 12:00 | "Good morning" displayed |
| 1.2.2 | Afternoon greeting | Load app 12:00-17:00 | "Good afternoon" displayed |
| 1.2.3 | Evening greeting | Load app after 17:00 | "Good evening" displayed |

---

## 2. Dashboard Flow

### 2.1 Dashboard Loading
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| 2.1.1 | Dashboard loads for user | Login, navigate to dashboard | All cards render |
| 2.1.2 | Empty state (no plan) | New user with no plan | "Generate Plan" button visible |
| 2.1.3 | Active plan state | User with generated plan | Today's workout summary shown |
| 2.1.4 | Weight widget displays | User with weight history | Current weight and 7D average shown |

### 2.2 Plan Generation
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| 2.2.1 | Generate weekly plan | Click "Generate Plan" | Button shows "Generating...", plan created |
| 2.2.2 | Plan includes workouts | Generate plan | 3-5 workout days based on profile |
| 2.2.3 | Plan includes meals | Generate plan | 7 days of meals with recipes |
| 2.2.4 | Shopping list generated | Generate plan | Consolidated ingredient list created |

### 2.3 Revision Cards
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| 2.3.1 | Pending revision shown | System creates revision | Card with approve/undo buttons |
| 2.3.2 | Approve revision | Click approve button | Status updates, dashboard refreshes |
| 2.3.3 | Undo revision | Click undo button | Revision reverted, plan restored |
| 2.3.4 | Revision history modal | Click "View History" | Modal shows revision timeline |

---

## 3. Workout Flow

### 3.1 Today's Workout
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| 3.1.1 | Workout day displays | Navigate to workout on training day | Exercise list shown |
| 3.1.2 | Rest day displays | Navigate to workout on rest day | "Rest Day" message shown |
| 3.1.3 | Exercise details | View workout | Sets, reps, notes visible |
| 3.1.4 | Active summary shown | Revision active | "This week's adjustments" banner |

### 3.2 Workout Logging
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| 3.2.1 | Complete workout | Click "Complete Workout" | Log created, navigate to dashboard |
| 3.2.2 | Workout logged with date | Complete workout | Timestamp recorded |
| 3.2.3 | Dashboard reflects completion | After logging | "Workout completed" indicator |

---

## 4. Meals Flow

### 4.1 Today's Meals
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| 4.1.1 | Meals display | Navigate to meals | Breakfast, lunch, dinner cards |
| 4.1.2 | Macro summary | View meals | Total calories, protein, carbs, fat |
| 4.1.3 | Recipe details | Click meal card | Ingredients and instructions shown |
| 4.1.4 | Active summary shown | Revision active | Calorie adjustment banner |

### 4.2 Shopping List
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| 4.2.1 | Shopping list loads | Navigate to shopping | Ingredient categories shown |
| 4.2.2 | Items grouped | View list | Grouped by category (produce, dairy, etc.) |
| 4.2.3 | Empty state | No active plan | "Generate plan first" message |

---

## 5. Progress Tracking

### 5.1 Weight Logging
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| 5.1.1 | Weight modal opens | Click weight icon | Modal with form displays |
| 5.1.2 | Log valid weight | Enter 75.5kg, submit | Weight saved, modal closes |
| 5.1.3 | Log with notes | Enter weight + notes | Both fields saved |
| 5.1.4 | Triggers adaptive replan | Log weight | Replan endpoint called |
| 5.1.5 | Dashboard updates | After logging | Weight widget refreshes |

### 5.2 Progress View
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| 5.2.1 | Weight chart renders | View progress | SVG chart with trend line |
| 5.2.2 | 7D average calculated | Multiple entries | Rolling average line shown |
| 5.2.3 | Stats display | View progress | Current, 7D avg, total change |
| 5.2.4 | Audit log shows | View progress | Weight entry history list |
| 5.2.5 | Empty state | No weight entries | "Need at least 2 logs" message |

---

## 6. Trends & Analytics

### 6.1 Trends Dashboard
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| 6.1.1 | Trends view loads | Navigate to trends | All 4 cards render |
| 6.1.2 | Goal banner status | View trends | on_track/mixed/off_track indicator |
| 6.1.3 | Weight trend card | View trends | Direction arrow, 4-week change |
| 6.1.4 | Workout card | View trends | Bar chart, avg completion % |
| 6.1.5 | Nutrition card | View trends | Bar chart, avg adherence % |
| 6.1.6 | Coach activity card | View trends | Total/auto/approved/undone counts |

### 6.2 Weekly Review
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| 6.2.1 | Review modal opens | Click "View Weekly Review" | Modal with detailed breakdown |
| 6.2.2 | Weight section | View review | Current, change, trend |
| 6.2.3 | Workout section | View review | Completed/planned, completion %, energy |
| 6.2.4 | Nutrition section | View review | Days on target, adherence %, avg calories |
| 6.2.5 | Insights display | View review | Bullet list of AI insights |
| 6.2.6 | Next action shown | View review | Recommended next step |

---

## 7. Adaptive Replanning

### 7.1 Weight-Triggered Replan
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| 7.1.1 | Significant weight change | Log weight diverging from goal | Revision created |
| 7.1.2 | Calorie adjustment | Fat loss + weight up | Negative calorie adjust proposed |
| 7.1.3 | Volume adjustment | Muscle gain + weight up | Positive volume modifier |
| 7.1.4 | Minor change ignored | Log weight within threshold | No revision created |

### 7.2 Revision Lifecycle
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| 7.2.1 | Pending → Approved | User approves | Status = "approved", changes applied |
| 7.2.2 | Pending → Applied | Auto-apply (low risk) | Status = "applied" |
| 7.2.3 | Applied → Reverted | User undoes | Status = "reverted" |
| 7.2.4 | Superseded handling | New revision created | Old revision = "superseded" |

---

## 8. Admin Operations

### 8.1 Seed Data
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| 8.1.1 | Seed demo data | POST /api/admin/seed/demo | Demo user created with full history |
| 8.1.2 | Check seed status | GET /api/admin/seed/demo/status | Returns seeded counts |
| 8.1.3 | Clear demo data | DELETE /api/admin/seed/demo | Demo user data removed |

### 8.2 Audit Export
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| 8.2.1 | Export user bundle | GET /api/admin/export/{user_id} | JSON with all user data |
| 8.2.2 | Bundle includes metadata | Export bundle | Version, timestamp, user_id |
| 8.2.3 | Bundle includes all tables | Export bundle | Profile, weights, plans, revisions, logs |

### 8.3 Audit Import
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| 8.3.1 | Preview valid bundle | POST /api/admin/import/preview | Validation passes, preview shown |
| 8.3.2 | Preview invalid bundle | Submit malformed JSON | Errors listed |
| 8.3.3 | Restore merge mode | POST /api/admin/import/restore?mode=merge | New records added, existing skipped |
| 8.3.4 | Restore replace mode | POST /api/admin/import/restore?mode=replace | Backup created, data replaced |
| 8.3.5 | Dry run mode | Submit with dry_run=true | No changes committed |
| 8.3.6 | Roundtrip integrity | Export → Clear → Import | Data matches original |

---

## 9. API Health & Edge Cases

### 9.1 API Validation
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| 9.1.1 | Health check | GET /api/health | 200 OK |
| 9.1.2 | Invalid user ID | GET /api/dashboard/invalid-id | 404 Not Found |
| 9.1.3 | Missing required field | POST /api/profile/ without goal | 422 Validation Error |
| 9.1.4 | Invalid date format | POST with malformed date | 422 Validation Error |

### 9.2 Edge Cases
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| 9.2.1 | No weight history | New user views progress | Empty state message |
| 9.2.2 | Single weight entry | One entry only | "Need at least 2 logs" |
| 9.2.3 | No active plan | View today's workout | "Generate plan" prompt |
| 9.2.4 | Past plan expired | Old plan, new week | "Generate new plan" prompt |
| 9.2.5 | Sparse trends data | < 4 weeks of data | Partial data handled gracefully |

---

## 10. Cross-Browser & PWA

### 10.1 Browser Compatibility
| # | Test Case | Browser | Expected Result |
|---|-----------|---------|-----------------|
| 10.1.1 | Chrome | Latest | Full functionality |
| 10.1.2 | Firefox | Latest | Full functionality |
| 10.1.3 | Safari | Latest | Full functionality |
| 10.1.4 | Edge | Latest | Full functionality |
| 10.1.5 | Mobile Chrome | Android | Responsive layout |
| 10.1.6 | Mobile Safari | iOS | Responsive layout |

### 10.2 PWA Features
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| 10.2.1 | Service worker registers | Load app | SW registered in DevTools |
| 10.2.2 | Manifest loads | Check Application tab | App info displayed |
| 10.2.3 | Add to homescreen | Use browser prompt | App icon on homescreen |
| 10.2.4 | Offline indication | Disable network | Graceful error handling |

---

## Test Execution Log

| Date | Tester | Sections Completed | Issues Found | Notes |
|------|--------|-------------------|--------------|-------|
| | | | | |

---

## Sign-Off

- [ ] All critical flows tested
- [ ] No blocking issues
- [ ] Edge cases handled
- [ ] Ready for v1 release

**QA Lead:** _________________ **Date:** _____________
