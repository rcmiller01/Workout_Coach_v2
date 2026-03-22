/**
 * AI Fitness Coach v1 — Trends Component
 *
 * Displays 4-week analytics dashboard with:
 * - Weight trend card
 * - Workout adherence trend card
 * - Nutrition adherence trend card
 * - Revision frequency card
 * - Goal alignment card
 */
const TrendsComponent = {
    async render(data) {
        const container = document.getElementById('trends-content');

        if (!data || data.message || !data.trends) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">📊</div>
                    <div class="empty-title">${data?.message || 'No trends data available'}</div>
                    <div class="empty-subtitle">Log workouts and weight for at least a week to see insights</div>
                </div>`;
            return;
        }

        const { trends, revision_frequency, goal_alignment, goal } = data;

        container.innerHTML = `
            <!-- Goal Alignment Banner -->
            ${this.renderGoalBanner(goal_alignment, goal)}

            <!-- Weight Trend Card -->
            ${this.renderWeightCard(trends.weight, goal)}

            <!-- Workout & Nutrition Grid -->
            <div class="trends-grid">
                ${this.renderWorkoutCard(trends.workouts)}
                ${this.renderNutritionCard(trends.nutrition)}
            </div>

            <!-- Coach Activity Card -->
            ${this.renderRevisionCard(revision_frequency)}

            <!-- Weekly Review Link -->
            <div class="card" style="margin-top:16px">
                <button class="btn-secondary" style="width:100%" onclick="TrendsComponent.showWeeklyReview()">
                    View This Week's Detailed Review
                </button>
            </div>
        `;
    },

    renderGoalBanner(alignment, goal) {
        const statusConfig = {
            'on_track': { icon: '✓', color: 'var(--accent-green)', label: 'On Track', bg: 'rgba(34,197,94,0.15)' },
            'mixed': { icon: '~', color: 'var(--accent-orange)', label: 'Some Areas Need Work', bg: 'rgba(251,146,60,0.15)' },
            'off_track': { icon: '!', color: 'var(--accent-red)', label: 'Needs Attention', bg: 'rgba(239,68,68,0.15)' },
            'insufficient_data': { icon: '?', color: 'var(--text-tertiary)', label: 'Gathering Data', bg: 'rgba(255,255,255,0.05)' }
        };

        const config = statusConfig[alignment.status] || statusConfig['insufficient_data'];
        const goalLabel = goal ? goal.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase()) : 'Goal';

        return `
            <div class="goal-banner" style="background:${config.bg};border-left:3px solid ${config.color}">
                <div class="goal-status">
                    <span class="goal-icon" style="background:${config.color}">${config.icon}</span>
                    <div>
                        <div class="goal-label">${goalLabel}</div>
                        <div class="goal-status-text" style="color:${config.color}">${config.label}</div>
                    </div>
                </div>
                <div class="goal-metrics">
                    <div class="goal-metric">
                        <span class="metric-value">${alignment.weight_aligned_weeks}/4</span>
                        <span class="metric-label">Weight</span>
                    </div>
                    <div class="goal-metric">
                        <span class="metric-value">${alignment.workout_target_weeks}/4</span>
                        <span class="metric-label">Workouts</span>
                    </div>
                    <div class="goal-metric">
                        <span class="metric-value">${alignment.nutrition_target_weeks}/4</span>
                        <span class="metric-label">Nutrition</span>
                    </div>
                </div>
            </div>`;
    },

    renderWeightCard(weight, goal) {
        const directionIcon = {
            'up': '↑',
            'down': '↓',
            'stable': '→',
            'insufficient_data': '—'
        };

        const directionColor = {
            'up': goal === 'muscle_gain' ? 'var(--accent-green)' : 'var(--accent-orange)',
            'down': goal === 'fat_loss' ? 'var(--accent-green)' : 'var(--accent-orange)',
            'stable': 'var(--accent-blue)',
            'insufficient_data': 'var(--text-tertiary)'
        };

        const totalChange = weight.total_change_kg !== null
            ? `${weight.total_change_kg > 0 ? '+' : ''}${weight.total_change_kg} kg`
            : '—';

        return `
            <div class="card trend-card">
                <div class="card-header">
                    <span class="card-label">Weight Trend</span>
                    <span class="trend-direction" style="color:${directionColor[weight.direction]}">
                        ${directionIcon[weight.direction]} ${weight.direction}
                    </span>
                </div>
                <div class="trend-chart-container">
                    ${this.generateWeightChart(weight.weeks)}
                </div>
                <div class="trend-summary">
                    <div class="trend-stat">
                        <span class="trend-stat-value">${totalChange}</span>
                        <span class="trend-stat-label">4-Week Change</span>
                    </div>
                </div>
            </div>`;
    },

    renderWorkoutCard(workouts) {
        const directionIcon = { 'up': '↑', 'down': '↓', 'stable': '→', 'insufficient_data': '—' };
        const avgPct = workouts.avg_completion_pct || 0;

        return `
            <div class="card trend-card">
                <div class="card-header">
                    <span class="card-label">Workouts</span>
                    <span class="trend-direction ${workouts.direction === 'up' ? 'trend-up' : workouts.direction === 'down' ? 'trend-down' : ''}">
                        ${directionIcon[workouts.direction]}
                    </span>
                </div>
                ${this.generateBarChart(workouts.weeks.map(w => ({ label: this.formatWeekLabel(w.week), value: w.completion_pct, max: 100 })), 'var(--accent-blue)')}
                <div class="trend-summary">
                    <span class="trend-stat-value">${avgPct.toFixed(0)}%</span>
                    <span class="trend-stat-label">Avg Completion</span>
                </div>
            </div>`;
    },

    renderNutritionCard(nutrition) {
        const directionIcon = { 'up': '↑', 'down': '↓', 'stable': '→', 'insufficient_data': '—' };
        const avgPct = nutrition.avg_adherence_pct || 0;

        return `
            <div class="card trend-card">
                <div class="card-header">
                    <span class="card-label">Nutrition</span>
                    <span class="trend-direction ${nutrition.direction === 'up' ? 'trend-up' : nutrition.direction === 'down' ? 'trend-down' : ''}">
                        ${directionIcon[nutrition.direction]}
                    </span>
                </div>
                ${this.generateBarChart(nutrition.weeks.map(w => ({ label: this.formatWeekLabel(w.week), value: w.adherence_pct, max: 100 })), 'var(--accent-purple)')}
                <div class="trend-summary">
                    <span class="trend-stat-value">${avgPct.toFixed(0)}%</span>
                    <span class="trend-stat-label">Avg Adherence</span>
                </div>
            </div>`;
    },

    renderRevisionCard(freq) {
        const assessmentConfig = {
            'stable': { color: 'var(--accent-green)', icon: '✓', desc: 'Coach is making minimal adjustments' },
            'moderate': { color: 'var(--accent-blue)', icon: '~', desc: 'Coach is actively fine-tuning your plan' },
            'active': { color: 'var(--accent-orange)', icon: '!', desc: 'Frequent adjustments - consider reviewing thresholds' }
        };

        const config = assessmentConfig[freq.assessment] || assessmentConfig['stable'];

        return `
            <div class="card" style="margin-top:16px">
                <div class="card-header">
                    <span class="card-label">Coach Activity</span>
                    <span class="card-badge" style="background:${config.color}">${freq.assessment}</span>
                </div>
                <div class="coach-activity-grid">
                    <div class="activity-stat">
                        <span class="activity-value">${freq.total}</span>
                        <span class="activity-label">Total Adjustments</span>
                    </div>
                    <div class="activity-stat">
                        <span class="activity-value">${freq.auto_applied}</span>
                        <span class="activity-label">Auto-Applied</span>
                    </div>
                    <div class="activity-stat">
                        <span class="activity-value">${freq.user_approved}</span>
                        <span class="activity-label">You Approved</span>
                    </div>
                    <div class="activity-stat">
                        <span class="activity-value">${freq.undone}</span>
                        <span class="activity-label">Undone</span>
                    </div>
                </div>
                <div class="coach-insight" style="border-top:1px solid var(--border-color);padding-top:12px;margin-top:12px">
                    <span style="color:${config.color};margin-right:8px">${config.icon}</span>
                    <span style="color:var(--text-secondary);font-size:13px">${config.desc}</span>
                </div>
            </div>`;
    },

    generateWeightChart(weeks) {
        if (!weeks || weeks.length < 2) {
            return `<div class="empty-state" style="padding:30px 0;font-size:13px">Need more data for chart</div>`;
        }

        const width = 320;
        const height = 100;
        const padding = 20;

        // Use cumulative change for visualization
        let cumulative = 0;
        const points = weeks.map(w => {
            cumulative += (w.change_kg || 0);
            return cumulative;
        });

        const minVal = Math.min(0, ...points) - 0.5;
        const maxVal = Math.max(0, ...points) + 0.5;
        const range = maxVal - minVal || 1;

        const getX = (idx) => padding + (idx * (width - 2 * padding) / (points.length - 1));
        const getY = (val) => height - padding - ((val - minVal) / range * (height - 2 * padding));

        const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${getX(i)} ${getY(p)}`).join(' ');
        const zeroY = getY(0);

        return `
            <svg class="trend-chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
                <line x1="${padding}" y1="${zeroY}" x2="${width - padding}" y2="${zeroY}" stroke="var(--border-color)" stroke-dasharray="4" />
                <path d="${path}" fill="none" stroke="var(--accent-blue)" stroke-width="2" />
                ${points.map((p, i) => `
                    <circle cx="${getX(i)}" cy="${getY(p)}" r="4" fill="${p < 0 ? 'var(--accent-green)' : p > 0 ? 'var(--accent-orange)' : 'var(--accent-blue)'}" />
                `).join('')}
            </svg>
            <div class="chart-labels">
                ${weeks.map(w => `<span>${this.formatWeekLabel(w.week)}</span>`).join('')}
            </div>`;
    },

    generateBarChart(data, color) {
        if (!data || data.length === 0) {
            return `<div class="empty-state" style="padding:20px 0;font-size:13px">No data</div>`;
        }

        return `
            <div class="bar-chart">
                ${data.map(d => {
                    const pct = Math.min(100, Math.max(0, (d.value / d.max) * 100));
                    return `
                        <div class="bar-item">
                            <div class="bar-track">
                                <div class="bar-fill" style="height:${pct}%;background:${color}"></div>
                            </div>
                            <span class="bar-value">${d.value.toFixed(0)}%</span>
                            <span class="bar-label">${d.label}</span>
                        </div>`;
                }).join('')}
            </div>`;
    },

    formatWeekLabel(dateStr) {
        if (!dateStr) return '—';
        const date = new Date(dateStr);
        return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    },

    async showWeeklyReview() {
        const userId = App.userId;
        if (!userId) return;

        try {
            const review = await api.getWeeklyReview(userId, 0);
            this.renderWeeklyReviewModal(review);
        } catch (err) {
            console.error('Failed to load weekly review:', err);
        }
    },

    renderWeeklyReviewModal(review) {
        const existingModal = document.querySelector('.modal-overlay');
        if (existingModal) existingModal.remove();

        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal-content">
                <div class="modal-header">
                    <h2>Weekly Review</h2>
                    <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">×</button>
                </div>
                <div class="modal-body">
                    <div class="review-period">
                        ${review.week_start} — ${review.week_end}
                    </div>

                    <!-- Weight Summary -->
                    <div class="review-section">
                        <h3>Weight</h3>
                        <div class="review-stats">
                            <div class="review-stat">
                                <span class="value">${review.weight.current_kg ?? '—'} kg</span>
                                <span class="label">Current</span>
                            </div>
                            <div class="review-stat">
                                <span class="value">${review.weight.change_kg !== null ? (review.weight.change_kg > 0 ? '+' : '') + review.weight.change_kg + ' kg' : '—'}</span>
                                <span class="label">Change</span>
                            </div>
                            <div class="review-stat">
                                <span class="value ${review.weight.aligned_with_goal ? 'positive' : ''}">${review.weight.trend || '—'}</span>
                                <span class="label">Trend</span>
                            </div>
                        </div>
                    </div>

                    <!-- Workouts -->
                    <div class="review-section">
                        <h3>Workouts</h3>
                        <div class="review-stats">
                            <div class="review-stat">
                                <span class="value">${review.workouts.completed}/${review.workouts.planned}</span>
                                <span class="label">Completed</span>
                            </div>
                            <div class="review-stat">
                                <span class="value">${review.workouts.completion_pct.toFixed(0)}%</span>
                                <span class="label">Completion</span>
                            </div>
                            <div class="review-stat">
                                <span class="value">${review.workouts.avg_energy ?? '—'}</span>
                                <span class="label">Avg Energy</span>
                            </div>
                        </div>
                    </div>

                    <!-- Nutrition -->
                    <div class="review-section">
                        <h3>Nutrition</h3>
                        <div class="review-stats">
                            <div class="review-stat">
                                <span class="value">${review.nutrition.days_on_target}/${review.nutrition.total_days}</span>
                                <span class="label">Days On Target</span>
                            </div>
                            <div class="review-stat">
                                <span class="value">${review.nutrition.adherence_pct.toFixed(0)}%</span>
                                <span class="label">Adherence</span>
                            </div>
                            <div class="review-stat">
                                <span class="value">${review.nutrition.avg_calories ?? '—'}</span>
                                <span class="label">Avg Calories</span>
                            </div>
                        </div>
                    </div>

                    <!-- Insights -->
                    ${review.insights && review.insights.length > 0 ? `
                        <div class="review-section">
                            <h3>Insights</h3>
                            <ul class="insights-list">
                                ${review.insights.map(i => `<li>${i}</li>`).join('')}
                            </ul>
                        </div>
                    ` : ''}

                    <!-- Next Action -->
                    ${review.next_action ? `
                        <div class="next-action-banner">
                            <strong>Next Step:</strong> ${review.next_action}
                        </div>
                    ` : ''}
                </div>
            </div>`;

        document.body.appendChild(modal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.remove();
        });
    }
};
