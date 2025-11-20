const token = localStorage.getItem('token');

if (!token) {
    window.location.href = '/login';
}

const DEFAULT_RANGE_DAYS = 7;

function logout() {
    localStorage.removeItem('token');
    window.location.href = '/login';
}

async function apiRequest(url) {
    const response = await fetch(url, {
        headers: {
            'Authorization': `Bearer ${token}`
        }
    });

    if (response.status === 401) {
        logout();
        return null;
    }

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || 'Ошибка запроса');
    }

    return response.json();
}

async function loadUserInfo() {
    try {
        const user = await apiRequest('/api/me');
        if (user) {
            document.getElementById('userInfo').textContent = `${user.full_name} (${user.role})`;
        }
    } catch (error) {
        console.error(error);
    }
}

function formatDate(date) {
    return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function setDefaultDates() {
    const fromInput = document.getElementById('dateFrom');
    const toInput = document.getElementById('dateTo');
    const today = new Date();
    const to = new Date(today);
    to.setDate(to.getDate() + DEFAULT_RANGE_DAYS);

    fromInput.value = today.toISOString().split('T')[0];
    toInput.value = to.toISOString().split('T')[0];
}

async function loadSchedule() {
    const fromInput = document.getElementById('dateFrom');
    const toInput = document.getElementById('dateTo');

    if (!fromInput.value || !toInput.value) {
        console.log('Выберите диапазон дат');
        return;
    }

    try {
        const params = new URLSearchParams({
            date_from: fromInput.value,
            date_to: toInput.value
        });
        const data = await apiRequest(`/api/my-schedule?${params.toString()}`);
        renderSchedule(data?.items || [], fromInput.value, toInput.value);
    } catch (error) {
        console.error(error);
        console.log(error.message);
    }
}

function renderSchedule(items, from, to) {
    const container = document.getElementById('scheduleContainer');
    if (!items.length) {
        container.innerHTML = `
            <div class="empty-state">
                <h3>Занятия не найдены</h3>
                <p>В выбранном диапазоне (${from} — ${to}) нет занятий</p>
            </div>
        `;
        return;
    }

    const grouped = {};
    items.forEach(item => {
        if (!grouped[item.date]) {
            grouped[item.date] = [];
        }
        grouped[item.date].push(item);
    });

    const dates = Object.keys(grouped).sort();
    container.innerHTML = dates.map(date => {
        const list = grouped[date]
            .sort((a, b) => a.time_start.localeCompare(b.time_start))
            .map(item => renderLesson(item))
            .join('');
        const displayDate = new Date(`${date}T00:00:00`);
        return `
            <div class="day-card">
                <h3>${formatDate(displayDate)}</h3>
                ${list}
            </div>
        `;
    }).join('');
}

function renderLesson(item) {
    const status = item.is_cancelled ? '<span class="badge" style="background:#fee2e2;color:#b91c1c;">Отменено</span>'
        : item.can_mark ? '<span class="badge" style="background:#dcfce7;color:#15803d;">Можно отметить</span>'
        : item.is_past ? '<span class="badge">Прошло</span>'
        : '<span class="badge" style="background:#e0f2fe;color:#0369a1;">Будет</span>';

    const disabled = !item.can_mark ? 'disabled style="opacity:0.6; cursor:not-allowed;"' : '';

    return `
        <div class="lesson-item">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <div style="font-weight:600; font-size:16px;">${item.discipline}</div>
                    <div style="font-size:14px; color:#475569;">${item.lesson_type} • ${item.time_start} - ${item.time_end}</div>
                </div>
                ${status}
            </div>
            <div class="lesson-meta">
                <div>Аудитория: <strong>${item.classroom || '—'}</strong></div>
                <div>Группы: <strong>${item.groups.map(g => g.name).join(', ')}</strong></div>
            </div>
            <div class="lesson-actions">
                <button class="btn btn-primary" ${disabled} onclick="openAttendance(${item.id})">
                    Отметить посещаемость
                </button>
            </div>
        </div>
    `;
}

function openAttendance(id) {
    window.location.href = `/attendance?schedule_id=${id}`;
}

document.addEventListener('DOMContentLoaded', async () => {
    loadUserInfo();
    setDefaultDates();
    loadSchedule();
});

