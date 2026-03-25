/**
 * AI Fitness Coach v1 — Dashboard Component
 *
 * Renders the main dashboard view with revision state awareness.
 */
const DashboardComponent = {
    async render(data) {
        if (!data) return;

        // Greeting
        const greetingEl = document.getElementById('greeting-text');
        if (greetingEl && data.greeting) {
            greetingEl.textContent = data.greeting;
        }

        // Coaching message
        const msgEl = document.getElementById('coaching-message');
        if (msgEl) {
            msgEl.textContent = data.coaching_message || '';
        }

        // Workout card
        const workout = data.workout;
        if (workout && !workout.is_rest_day) {
            document.getElementById('workout-focus').textContent = workout.focus || 'Workout';
            document.getElementById('workout-duration').textContent = workout.estimated_duration_min || '--';
            document.getElementById('workout-exercises').textContent =
                (workout.exercises || []).length;

            const statusBadge = document.getElementById('workout-status');
            if (data.workout_completed) {
                statusBadge.textContent = 'Complete ✓';
                statusBadge.classList.add('completed');
            } else {
                statusBadge.textContent = 'Pending';
                statusBadge.classList.remove('completed');
            }
        } else if (workout && workout.is_rest_day) {
            document.getElementById('workout-focus').textContent = '🧘 Rest Day';
            document.getElementById('workout-duration').textContent = '0';
            document.getElementById('workout-exercises').textContent = '0';
            document.getElementById('workout-status').textContent = 'Rest';
            document.getElementById('btn-start-workout').style.display = 'none';
        } else {
            document.getElementById('workout-focus').textContent = 'No plan yet';
            document.getElementById('btn-start-workout').textContent = 'Generate Plan →';
        }

        // Macro rings — show actuals vs targets
        const targets = data.macro_targets || {};
        const actuals = data.macro_actuals || {};
        if (targets.calories) {
            const aCal = actuals.calories || 0;
            document.getElementById('val-calories').textContent = aCal > 0 ? `${aCal}` : targets.calories;
            this.setRingProgress('ring-calories-fill', targets.calories > 0 ? Math.min(1, aCal / targets.calories) : 0);
        }
        if (targets.protein_g) {
            const aPro = actuals.protein_g || 0;
            document.getElementById('val-protein').textContent = aPro > 0 ? `${Math.round(aPro)}` : targets.protein_g;
            this.setRingProgress('ring-protein-fill', targets.protein_g > 0 ? Math.min(1, aPro / targets.protein_g) : 0);
        }
        if (targets.carbs_g) {
            const aCarb = actuals.carbs_g || 0;
            document.getElementById('val-carbs').textContent = aCarb > 0 ? `${Math.round(aCarb)}` : targets.carbs_g;
            this.setRingProgress('ring-carbs-fill', targets.carbs_g > 0 ? Math.min(1, aCarb / targets.carbs_g) : 0);
        }

        // Stats (with null-safe element access) - display in lbs
        const weightEl = document.getElementById('stat-weight');
        if (weightEl) {
            weightEl.textContent = data.current_weight_kg
                ? (data.current_weight_kg * 2.20462).toFixed(1)
                : '--';
        }
        const adherenceEl = document.getElementById('stat-adherence');
        if (adherenceEl) {
            adherenceEl.textContent = (data.weekly_adherence_pct !== null && data.weekly_adherence_pct !== undefined)
                ? `${Math.round(data.weekly_adherence_pct)}%`
                : '--';
        }

        // Next workout
        if (data.next_workout) {
            document.getElementById('next-workout-day').textContent = data.next_workout.day;
            document.getElementById('next-workout-focus').textContent = data.next_workout.focus;
        }

        // Plan Adjustments (Revisions)
        this.renderReplanningBanner(data.revisions);
    },

    /**
     * Returns visual config for a given revision status.
     */
    _getStatusConfig(status) {
        const configs = {
            pending: {
                color: 'var(--accent-purple)',
                bgColor: 'var(--accent-purple-glow, rgba(139,92,246,0.15))',
                icon: '⏳',
                label: 'Pending Approval',
            },
            applied: {
                color: 'var(--accent-blue, #3b82f6)',
                bgColor: 'rgba(59,130,246,0.15)',
                icon: '⚡',
                label: 'Auto-Applied',
            },
            approved: {
                color: 'var(--accent-green)',
                bgColor: 'var(--accent-green-glow, rgba(34,197,94,0.15))',
                icon: '✅',
                label: 'Approved',
            },
            reverted: {
                color: 'var(--text-tertiary, #6b7280)',
                bgColor: 'rgba(107,114,128,0.1)',
                icon: '↩️',
                label: 'Reverted',
            },
            superseded: {
                color: 'var(--accent-amber, #f59e0b)',
                bgColor: 'rgba(245,158,11,0.1)',
                icon: '⏭️',
                label: 'Superseded',
            },
            blocked: {
                color: 'var(--accent-red, #ef4444)',
                bgColor: 'rgba(239,68,68,0.1)',
                icon: '🚫',
                label: 'Blocked',
            },
        };
        return configs[status] || configs.applied;
    },

    /**
     * Renders the replanning banner for the most recent actionable revision.
     */
    renderReplanningBanner(revisions) {
        const banner = document.getElementById('replanning-banner');
        if (!banner || !revisions || revisions.length === 0) {
            if (banner) banner.style.display = 'none';
            return;
        }

        // Find the latest actionable revision (pending or applied, not terminal)
        const TERMINAL = new Set(['reverted', 'superseded', 'blocked']);
        const actionable = revisions.find(r => !TERMINAL.has(r.status));
        const lastAckId = localStorage.getItem('last_ack_revision');

        // No actionable revision or already acknowledged
        if (!actionable || (actionable.status !== 'pending' && actionable.id === lastAckId)) {
            banner.style.display = 'none';
            return;
        }

        const config = this._getStatusConfig(actionable.status);
        const isPending = actionable.status === 'pending';
        const isApplied = actionable.status === 'applied';

        const title = isPending ? 'New Plan Proposal' : 'Plan Auto-Adjusted';
        const areaLabel = this._formatAreaLabel(actionable.target_area);

        banner.innerHTML = `
            <div class="replanning-header">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
                    <path d="M12 8v4"></path>
                    <path d="M12 16h.01"></path>
                </svg>
                <span class="replanning-title">${title}</span>
                ${areaLabel ? `<span class="replanning-area-badge" style="background:${config.bgColor}; color:${config.color}; font-size:11px; padding:2px 8px; border-radius:8px; margin-left:auto;">${areaLabel}</span>` : ''}
            </div>
            <p class="replanning-reason">${actionable.reason}</p>
            ${actionable.status_label ? `<p class="replanning-status-label" style="font-size:12px; color:${config.color}; margin:4px 0 8px;">${config.icon} ${actionable.status_label}</p>` : ''}
            <div class="replanning-actions">
                ${isPending ? '<button class="btn-replan-ack" id="btn-approve-replan">Approve Change</button>' : ''}
                ${isApplied ? '<button class="btn-replan-undo" id="btn-undo-replan">Undo Adjustment</button>' : ''}
                ${!isPending ? '<button class="btn-replan-ack" id="btn-ack-replan">Acknowledge</button>' : ''}
                <button class="btn-replan-details" id="btn-see-history">See History</button>
            </div>
        `;
        banner.style.display = 'block';

        // --- Event Bindings ---

        // History button
        document.getElementById('btn-see-history')?.addEventListener('click', () => {
            App.showRevisionHistory();
        });

        // Approve (pending)
        if (isPending) {
            document.getElementById('btn-approve-replan')?.addEventListener('click', async () => {
                const approveBtn = document.getElementById('btn-approve-replan');
                await App._runAction('approveReplan', async () => {
                    await api.approveReplan(actionable.id);
                    localStorage.setItem('last_ack_revision', actionable.id);
                    App.loadViewData('dashboard');
                }, {
                    btn: approveBtn,
                    loadingText: 'Approving…',
                    defaultText: 'Approve Change',
                    errorPrefix: 'Approval failed',
                });
            });
        }

        // Undo (auto-applied)
        if (isApplied) {
            document.getElementById('btn-undo-replan')?.addEventListener('click', async () => {
                const undoBtn = document.getElementById('btn-undo-replan');
                await App._runAction('undoReplan', async () => {
                    await api.undoReplan(actionable.id);
                    localStorage.setItem('last_ack_revision', actionable.id);

                    // Show confirmation
                    banner.innerHTML = `
                        <div style="text-align:center; padding:10px; color:var(--accent-green)">
                            <strong>✓ Coach adjustment reverted</strong>
                            <p style="font-size:12px; margin:4px 0 0">Plan restored. Revision marked as reverted.</p>
                        </div>
                    `;
                    setTimeout(() => App.loadViewData('dashboard'), 2000);
                }, {
                    btn: undoBtn,
                    loadingText: 'Reverting…',
                    defaultText: 'Undo Adjustment',
                    errorPrefix: 'Undo failed',
                });
            });
        }

        // Acknowledge (non-pending)
        if (!isPending) {
            document.getElementById('btn-ack-replan')?.addEventListener('click', () => {
                localStorage.setItem('last_ack_revision', actionable.id);
                banner.style.display = 'none';
            });
        }
    },

    /**
     * Returns a human-readable label for the target area.
     */
    _formatAreaLabel(area) {
        const labels = {
            workout: '🏋️ Workout',
            nutrition: '🥗 Nutrition',
            both: '📋 Full Plan',
        };
        return labels[area] || '';
    },

    setRingProgress(elementId, progress) {
        const el = document.getElementById(elementId);
        if (el) {
            el.style.setProperty('--progress', Math.min(1, Math.max(0, progress)));
        }
    }
};
