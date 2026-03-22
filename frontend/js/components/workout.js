/**
 * AI Fitness Coach v1 — Workout Component
 */
const WorkoutComponent = {
    async render(data) {
        const container = document.getElementById('workout-content');
        if (!data || !data.workout) {
            container.innerHTML = `
                <div class="empty-state">
                    <p>No workout planned for today.</p>
                    <button class="btn-secondary" onclick="App.generatePlan()">Generate Plan</button>
                </div>`;
            return;
        }

        const workout = data.workout;

        if (workout.is_rest_day) {
            container.innerHTML = `
                <div class="rest-day-indicator">
                    <div class="emoji">🧘</div>
                    <p>Rest Day — Time to recover!</p>
                    <p style="color: var(--text-tertiary); font-size: 14px; margin-top: 8px;">
                        Active recovery like walking or light stretching is encouraged.
                    </p>
                </div>`;
            return;
        }

        let html = '';

        if (data.active_summary) {
            html += `
                <div style="background: rgba(79, 140, 255, 0.1); border: 1px solid rgba(79, 140, 255, 0.2); padding: 8px 12px; border-radius: 6px; margin-bottom: 16px; font-size: 13px; color: var(--accent-blue);">
                    <strong>ℹ️</strong> ${data.active_summary}
                </div>
            `;
        }

        if (workout.warmup_notes) {
            html += `
                <div class="card" style="margin-bottom: 16px; border-color: rgba(245, 158, 11, 0.2);">
                    <div class="card-header">
                        <span class="card-label">Warm-up</span>
                    </div>
                    <p style="font-size: 14px; color: var(--text-secondary);">${workout.warmup_notes}</p>
                </div>`;
        }

        html += '<div class="exercise-list">';

        (workout.exercises || []).forEach((ex, idx) => {
            html += `
                <div class="exercise-card" id="exercise-${idx}" data-index="${idx}">
                    <div class="exercise-muscle">${ex.muscle_group || ''}</div>
                    <div class="exercise-name">${ex.name}</div>
                    ${ex.notes ? `<div style="font-size: 11px; color: var(--accent-amber); margin-bottom: 8px; font-style: italic;">↳ ${ex.notes}</div>` : ''}
                    <div class="exercise-detail">
                        <span><strong>${ex.sets}</strong> sets</span>
                        <span><strong>${ex.reps}</strong> reps</span>
                        ${ex.weight_kg ? `<span><strong>${ex.weight_kg}</strong> kg</span>` : ''}
                        <span><strong>${ex.rest_sec || 90}</strong>s rest</span>
                    </div>
                    ${ex.substitutions && ex.substitutions.length > 0 ?
                        `<div style="margin-top: 8px; font-size: 12px; color: var(--text-tertiary);">
                            Swap: ${ex.substitutions.join(', ')}
                        </div>` : ''
                    }
                </div>`;
        });

        html += '</div>';

        if (workout.cooldown_notes) {
            html += `
                <div class="card" style="margin-top: 16px; border-color: rgba(79, 140, 255, 0.2);">
                    <div class="card-header">
                        <span class="card-label">Cool-down</span>
                    </div>
                    <p style="font-size: 14px; color: var(--text-secondary);">${workout.cooldown_notes}</p>
                </div>`;
        }

        html += `
            <div style="padding: 20px 0;">
                <button class="btn-primary btn-full" id="btn-complete-workout" onclick="App.completeWorkout()">
                    Complete Workout ✓
                </button>
            </div>`;

        container.innerHTML = html;

        // Add tap-to-complete on exercise cards
        container.querySelectorAll('.exercise-card').forEach(card => {
            card.addEventListener('click', () => {
                card.classList.toggle('exercise-completed');
            });
        });
    }
};
