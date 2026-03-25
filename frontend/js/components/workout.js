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
                </div>
                <div style="padding: 16px 0;">
                    <button class="btn-secondary" onclick="WorkoutComponent.showAddCardioForm()" style="width: 100%; margin-bottom: 8px;">
                        ＋ Log Cardio / Active Recovery
                    </button>
                </div>
                <div id="adhoc-exercises"></div>`;
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

        if (data.completed) {
            html += `
                <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.2); padding: 12px; border-radius: 8px; margin-bottom: 16px; text-align: center;">
                    <span style="color: var(--accent-green, #10b981); font-weight: 600;">✓ Workout completed today</span>
                </div>`;
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

        // ─── Exercise List ───
        html += '<div class="exercise-list" id="exercise-list">';

        (workout.exercises || []).forEach((ex, idx) => {
            html += this._renderExerciseCard(ex, idx, 'planned');
        });

        html += '</div>';

        // ─── Ad-hoc exercises container ───
        html += '<div id="adhoc-exercises"></div>';

        if (workout.cooldown_notes) {
            html += `
                <div class="card" style="margin-top: 16px; border-color: rgba(79, 140, 255, 0.2);">
                    <div class="card-header">
                        <span class="card-label">Cool-down</span>
                    </div>
                    <p style="font-size: 14px; color: var(--text-secondary);">${workout.cooldown_notes}</p>
                </div>`;
        }

        // ─── Action Buttons ───
        html += `
            <div style="padding: 16px 0; display: flex; flex-direction: column; gap: 8px;">
                <div style="display: flex; gap: 8px;">
                    <button class="btn-secondary" onclick="WorkoutComponent.showAddExerciseForm()" style="flex: 1; padding: 10px; font-size: 13px;">
                        ＋ Add Exercise
                    </button>
                    <button class="btn-secondary" onclick="WorkoutComponent.showAddCardioForm()" style="flex: 1; padding: 10px; font-size: 13px;">
                        ＋ Add Cardio
                    </button>
                </div>
                ${!data.completed ? `
                <button class="btn-primary btn-full" id="btn-complete-workout" onclick="App.completeWorkout()" style="margin-top: 8px;">
                    Complete Workout ✓
                </button>` : ''}
            </div>`;

        // ─── Add Exercise Form (hidden by default) ───
        html += `
            <div id="add-exercise-form" style="display: none;" class="card" >
                <h4 style="margin: 0 0 12px; color: var(--text-primary);">Add Exercise</h4>
                <div style="display: flex; flex-direction: column; gap: 8px;">
                    <input type="text" id="adhoc-name" placeholder="Exercise name" style="padding: 8px; background: rgba(255,255,255,0.05); border: 1px solid var(--border-card); border-radius: 6px; color: var(--text-primary);">
                    <input type="text" id="adhoc-muscle" placeholder="Muscle group (e.g. chest, back)" value="other" style="padding: 8px; background: rgba(255,255,255,0.05); border: 1px solid var(--border-card); border-radius: 6px; color: var(--text-primary);">
                    <div style="display: flex; gap: 8px;">
                        <input type="number" id="adhoc-sets" placeholder="Sets" value="3" style="flex:1; padding: 8px; background: rgba(255,255,255,0.05); border: 1px solid var(--border-card); border-radius: 6px; color: var(--text-primary);">
                        <input type="number" id="adhoc-reps" placeholder="Reps" value="10" style="flex:1; padding: 8px; background: rgba(255,255,255,0.05); border: 1px solid var(--border-card); border-radius: 6px; color: var(--text-primary);">
                        <input type="number" id="adhoc-weight" placeholder="Weight (kg)" value="0" style="flex:1; padding: 8px; background: rgba(255,255,255,0.05); border: 1px solid var(--border-card); border-radius: 6px; color: var(--text-primary);">
                    </div>
                    <div style="display: flex; gap: 8px;">
                        <button class="btn-primary" onclick="WorkoutComponent.addExercise()" style="flex: 1; padding: 8px;">Add</button>
                        <button class="btn-secondary" onclick="document.getElementById('add-exercise-form').style.display='none'" style="flex: 1; padding: 8px;">Cancel</button>
                    </div>
                </div>
            </div>`;

        // ─── Add Cardio Form (hidden by default) ───
        html += `
            <div id="add-cardio-form" style="display: none;" class="card">
                <h4 style="margin: 0 0 12px; color: var(--text-primary);">Add Cardio</h4>
                <div style="display: flex; flex-direction: column; gap: 8px;">
                    <input type="text" id="cardio-name" placeholder="Activity (running, cycling, etc.)" style="padding: 8px; background: rgba(255,255,255,0.05); border: 1px solid var(--border-card); border-radius: 6px; color: var(--text-primary);">
                    <div style="display: flex; gap: 8px;">
                        <input type="number" id="cardio-duration" placeholder="Duration (min)" value="30" style="flex:1; padding: 8px; background: rgba(255,255,255,0.05); border: 1px solid var(--border-card); border-radius: 6px; color: var(--text-primary);">
                        <input type="number" id="cardio-distance" placeholder="Distance (km)" step="0.1" style="flex:1; padding: 8px; background: rgba(255,255,255,0.05); border: 1px solid var(--border-card); border-radius: 6px; color: var(--text-primary);">
                    </div>
                    <div style="display: flex; gap: 8px;">
                        <button class="btn-primary" onclick="WorkoutComponent.addCardio()" style="flex: 1; padding: 8px;">Add</button>
                        <button class="btn-secondary" onclick="document.getElementById('add-cardio-form').style.display='none'" style="flex: 1; padding: 8px;">Cancel</button>
                    </div>
                </div>
            </div>`;

        container.innerHTML = html;

        // ─── Add tap-to-toggle on exercise cards ───
        container.querySelectorAll('.exercise-card[data-source="planned"]').forEach(card => {
            const checkbox = card.querySelector('.exercise-toggle');
            card.addEventListener('click', (e) => {
                // Don't toggle if clicking on the delete button or weight input
                if (e.target.closest('.exercise-delete') || e.target.closest('.exercise-weight-input')) return;
                if (checkbox) {
                    checkbox.checked = !checkbox.checked;
                    card.classList.toggle('exercise-completed', checkbox.checked);
                    card.classList.toggle('exercise-skipped', !checkbox.checked);
                }
            });
        });
    },

    _renderExerciseCard(ex, idx, source) {
        const isCardio = source === 'cardio';
        const isAdhoc = source === 'adhoc';
        const borderColor = isCardio ? 'var(--accent-amber, #f59e0b)' : isAdhoc ? 'var(--accent-purple, #8b5cf6)' : 'transparent';
        const badgeHtml = isCardio ? '<span style="font-size: 10px; padding: 1px 6px; background: rgba(245,158,11,0.15); color: var(--accent-amber); border-radius: 4px;">Cardio</span>'
            : isAdhoc ? '<span style="font-size: 10px; padding: 1px 6px; background: rgba(139,92,246,0.15); color: var(--accent-purple, #8b5cf6); border-radius: 4px;">Custom</span>'
            : '';

        if (isCardio) {
            return `
                <div class="exercise-card exercise-completed" data-index="${idx}" data-source="cardio" style="border-left: 3px solid ${borderColor};">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <span class="exercise-muscle">🏃 Cardio</span>
                            ${badgeHtml}
                        </div>
                        <button class="exercise-delete" onclick="WorkoutComponent.removeExercise(${idx})" title="Remove" style="background: none; border: none; color: var(--accent-red, #ef4444); cursor: pointer; font-size: 14px; opacity: 0.6;">✕</button>
                    </div>
                    <div class="exercise-name">${ex.name}</div>
                    <div class="exercise-detail" style="margin-top: 8px;">
                        ${ex.duration_min ? `<span><strong>${ex.duration_min}</strong> min</span>` : ''}
                        ${ex.distance_km ? `<span><strong>${ex.distance_km}</strong> km</span>` : ''}
                    </div>
                </div>`;
        }

        return `
            <div class="exercise-card ${source === 'planned' ? '' : 'exercise-completed'}" data-index="${idx}" data-source="${source}" style="border-left: 3px solid ${borderColor}; cursor: pointer;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <input type="checkbox" class="exercise-toggle" ${source !== 'planned' ? 'checked' : 'checked'} style="width: 18px; height: 18px; accent-color: var(--accent-green, #10b981);">
                        <span class="exercise-muscle">${ex.muscle_group || ''}</span>
                        ${badgeHtml}
                    </div>
                    <button class="exercise-delete" onclick="event.stopPropagation(); WorkoutComponent.removeExercise(${idx})" title="Remove" style="background: none; border: none; color: var(--accent-red, #ef4444); cursor: pointer; font-size: 14px; opacity: 0.6;">✕</button>
                </div>
                <div class="exercise-name">${ex.name}</div>
                ${ex.notes ? `<div style="font-size: 11px; color: var(--accent-amber); margin-bottom: 8px; font-style: italic;">↳ ${ex.notes}</div>` : ''}
                <div class="exercise-detail" style="margin-top: 8px;">
                    <span><strong>${ex.sets}</strong> sets</span>
                    <span><strong>${ex.reps}</strong> reps</span>
                    <span>
                        <input type="number" class="exercise-weight-input" value="${ex.weight_kg || 0}" step="0.5" min="0"
                            onclick="event.stopPropagation()"
                            style="width: 55px; padding: 2px 4px; background: rgba(255,255,255,0.08); border: 1px solid var(--border-card); border-radius: 4px; color: var(--text-primary); text-align: center; font-size: 13px;">
                        kg
                    </span>
                    <span><strong>${ex.rest_sec || 90}</strong>s rest</span>
                </div>
                ${ex.substitutions && ex.substitutions.length > 0 ?
                    `<div style="margin-top: 8px; font-size: 12px; color: var(--text-tertiary);">
                        Swap: ${ex.substitutions.join(', ')}
                    </div>` : ''
                }
            </div>`;
    },

    // ─── Ad-hoc Exercise Management ───

    _adhocExercises: [],

    showAddExerciseForm() {
        document.getElementById('add-exercise-form').style.display = 'block';
        document.getElementById('add-cardio-form').style.display = 'none';
        document.getElementById('adhoc-name').focus();
    },

    showAddCardioForm() {
        document.getElementById('add-cardio-form').style.display = 'block';
        const exForm = document.getElementById('add-exercise-form');
        if (exForm) exForm.style.display = 'none';
        document.getElementById('cardio-name').focus();
    },

    addExercise() {
        const name = document.getElementById('adhoc-name').value.trim();
        if (!name) return alert('Please enter an exercise name');

        const exercise = {
            name,
            muscle_group: document.getElementById('adhoc-muscle').value.trim() || 'other',
            sets: parseInt(document.getElementById('adhoc-sets').value) || 3,
            reps: parseInt(document.getElementById('adhoc-reps').value) || 10,
            weight_kg: parseFloat(document.getElementById('adhoc-weight').value) || 0,
            rest_sec: 90,
            source: 'adhoc',
            completed: true,
        };

        this._adhocExercises.push(exercise);
        this._renderAdhocExercises();
        document.getElementById('add-exercise-form').style.display = 'none';
        // Reset form
        document.getElementById('adhoc-name').value = '';
    },

    addCardio() {
        const name = document.getElementById('cardio-name').value.trim();
        if (!name) return alert('Please enter an activity name');

        const cardio = {
            name,
            muscle_group: 'cardio',
            sets: 1,
            reps: 0,
            weight_kg: 0,
            duration_min: parseInt(document.getElementById('cardio-duration').value) || 30,
            distance_km: parseFloat(document.getElementById('cardio-distance').value) || null,
            source: 'cardio',
            completed: true,
        };

        this._adhocExercises.push(cardio);
        this._renderAdhocExercises();
        document.getElementById('add-cardio-form').style.display = 'none';
        document.getElementById('cardio-name').value = '';
    },

    removeExercise(idx) {
        // Check if it's an adhoc exercise (index >= planned count)
        const plannedCards = document.querySelectorAll('.exercise-card[data-source="planned"]');
        const plannedCount = plannedCards.length;

        if (idx >= plannedCount) {
            // Remove from adhoc list
            const adhocIdx = idx - plannedCount;
            this._adhocExercises.splice(adhocIdx, 1);
            this._renderAdhocExercises();
        } else {
            // Mark planned exercise as skipped (strikethrough)
            const card = document.querySelector(`.exercise-card[data-index="${idx}"][data-source="planned"]`);
            if (card) {
                const checkbox = card.querySelector('.exercise-toggle');
                if (checkbox) checkbox.checked = false;
                card.classList.add('exercise-skipped');
                card.classList.remove('exercise-completed');
                card.style.opacity = '0.4';
                card.style.textDecoration = 'line-through';
            }
        }
    },

    _renderAdhocExercises() {
        const container = document.getElementById('adhoc-exercises');
        if (!container) return;

        const plannedCount = document.querySelectorAll('.exercise-card[data-source="planned"]').length;
        let html = '';

        if (this._adhocExercises.length > 0) {
            html += '<h3 style="margin: 16px 0 8px; font-size: 14px; color: var(--text-secondary);">Added Exercises</h3>';
        }

        this._adhocExercises.forEach((ex, i) => {
            const globalIdx = plannedCount + i;
            html += this._renderExerciseCard(ex, globalIdx, ex.source || 'adhoc');
        });

        container.innerHTML = html;
    },

    // ─── Collect workout data for completion ───

    collectWorkoutData() {
        const exercises = [];
        const cards = document.querySelectorAll('.exercise-card');

        cards.forEach(card => {
            const source = card.dataset.source || 'planned';
            const checkbox = card.querySelector('.exercise-toggle');
            const completed = checkbox ? checkbox.checked : true;
            const weightInput = card.querySelector('.exercise-weight-input');
            const name = card.querySelector('.exercise-name')?.textContent?.trim() || '';

            // Get details from exercise-detail spans
            const details = card.querySelectorAll('.exercise-detail span');
            let sets = 0, reps = 0, weight_kg = 0, rest_sec = 90, duration_min = 0, distance_km = 0;

            details.forEach(span => {
                const text = span.textContent.trim();
                const strong = span.querySelector('strong');
                if (!strong) return;
                const val = strong.textContent.trim();
                if (text.includes('sets')) sets = parseInt(val) || 0;
                else if (text.includes('reps')) reps = parseInt(val) || 0;
                else if (text.includes('rest')) rest_sec = parseInt(val) || 90;
                else if (text.includes('min')) duration_min = parseInt(val) || 0;
                else if (text.includes('km')) distance_km = parseFloat(val) || 0;
            });

            if (weightInput) weight_kg = parseFloat(weightInput.value) || 0;

            const muscle = card.querySelector('.exercise-muscle')?.textContent?.trim() || '';

            exercises.push({
                name,
                muscle_group: muscle,
                sets,
                reps,
                weight_kg,
                rest_sec,
                duration_min: duration_min || null,
                distance_km: distance_km || null,
                source,
                completed,
            });
        });

        // Calculate completion % based on planned exercises only
        const planned = exercises.filter(e => e.source === 'planned');
        const completedPlanned = planned.filter(e => e.completed);
        const completion_pct = planned.length > 0 ? completedPlanned.length / planned.length : 1;

        return { exercises, completion_pct };
    },

    formatMuscleGroup(mg) {
        const labels = {
            chest: '💪 Chest', back: '🔙 Back', legs: '🦵 Legs',
            shoulders: '🏋️ Shoulders', arms: '💪 Arms', core: '🎯 Core',
            cardio: '🏃 Cardio', other: '⚡ Other',
        };
        return labels[(mg || '').toLowerCase()] || mg;
    }
};
