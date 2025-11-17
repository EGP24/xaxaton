// Основные переменные
let token = localStorage.getItem('token');
let currentWeekFilter = 'odd';

// Проверка авторизации
if (!token) {
    window.location.href = '/login';
}

// Функция выхода
function logout() {
    localStorage.removeItem('token');
    window.location.href = '/login';
}

// API запросы
async function apiRequest(url, options = {}) {
    try {
        const response = await fetch(url, {
            ...options,
            headers: {
                ...options.headers,
                'Authorization': `Bearer ${token}`
            }
        });

        if (response.status === 401) {
            logout();
            return null;
        }

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Ошибка запроса');
        }

        return response.json();
    } catch (error) {
        console.error('API request failed:', error);
        throw error;
    }
}

// Переключение вкладок
function switchTab(tabName) {
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

    event.target.classList.add('active');
    document.getElementById(tabName).classList.add('active');

    if (tabName === 'students') loadStudents();
    if (tabName === 'groups') loadGroups();
    if (tabName === 'disciplines') loadDisciplines();
    if (tabName === 'semesters') loadSemesters();
    if (tabName === 'schedule') loadScheduleTemplates();
}

// Загрузка информации о пользователе
async function loadUserInfo() {
    try {
        const user = await apiRequest('/api/me');
        if (user && user.full_name) {
            document.getElementById('userName').textContent = user.full_name;
        }
    } catch (error) {
        console.error('Ошибка загрузки информации о пользователе:', error);
    }
}

// ============ СТУДЕНТЫ ============

async function loadStudents() {
    try {
        const students = await apiRequest('/api/students');
        const container = document.getElementById('studentsList');

        if (!students || students.length === 0) {
            container.innerHTML = '<p style="text-align: center; color: #999; padding: 20px;">Студентов пока нет</p>';
            return;
        }

        container.innerHTML = students.map(s => `
            <div class="list-item">
                <div>
                    <strong>${s.full_name}</strong>
                    <span class="badge badge-blue">${s.group_name}</span>
                </div>
                <button class="btn btn-danger" onclick="deleteStudent(${s.id})">Удалить</button>
            </div>
        `).join('');
    } catch (error) {
        console.error('Ошибка загрузки студентов:', error);
    }
}

function openStudentModal() {
    loadGroupsForSelect('studentGroup');
    document.getElementById('studentModal').classList.add('active');
}

async function loadGroupsForSelect(selectId) {
    try {
        const groups = await apiRequest('/api/groups');
        const select = document.getElementById(selectId);
        select.innerHTML = '<option value="">Выберите группу</option>' +
            groups.map(g => `<option value="${g.id}">${g.name}</option>`).join('');
    } catch (error) {
        console.error('Ошибка загрузки групп:', error);
    }
}

document.getElementById('studentForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const alertDiv = document.getElementById('studentAlert');

    try {
        const formData = new URLSearchParams();
        formData.append('full_name', document.getElementById('studentName').value);
        formData.append('group_id', document.getElementById('studentGroup').value);

        await fetch('/api/admin/students', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': `Bearer ${token}`
            },
            body: formData
        });

        alertDiv.innerHTML = '<div class="alert alert-success">Студент успешно добавлен!</div>';
        document.getElementById('studentForm').reset();
        setTimeout(() => {
            closeModal('studentModal');
            loadStudents();
        }, 1500);
    } catch (error) {
        alertDiv.innerHTML = `<div class="alert alert-error">Ошибка: ${error.message}</div>`;
    }
});

async function deleteStudent(id) {
    if (!confirm('Удалить студента?')) return;

    try {
        await fetch(`/api/admin/students/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        loadStudents();
    } catch (error) {
        alert('Ошибка удаления студента');
    }
}

// ============ ГРУППЫ ============

async function loadGroups() {
    try {
        const groups = await apiRequest('/api/groups');
        const container = document.getElementById('groupsList');

        if (!groups || groups.length === 0) {
            container.innerHTML = '<p style="text-align: center; color: #999; padding: 20px;">Групп пока нет</p>';
            return;
        }

        container.innerHTML = groups.map(g => `
            <div class="list-item">
                <strong>${g.name}</strong>
                <button class="btn btn-danger" onclick="deleteGroup(${g.id})">Удалить</button>
            </div>
        `).join('');
    } catch (error) {
        console.error('Ошибка загрузки групп:', error);
    }
}

function openGroupModal() {
    document.getElementById('groupModal').classList.add('active');
}

document.getElementById('groupForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const alertDiv = document.getElementById('groupAlert');

    try {
        const formData = new URLSearchParams();
        formData.append('name', document.getElementById('groupName').value);

        await fetch('/api/admin/groups', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': `Bearer ${token}`
            },
            body: formData
        });

        alertDiv.innerHTML = '<div class="alert alert-success">Группа успешно добавлена!</div>';
        document.getElementById('groupForm').reset();
        setTimeout(() => {
            closeModal('groupModal');
            loadGroups();
        }, 1500);
    } catch (error) {
        alertDiv.innerHTML = `<div class="alert alert-error">Ошибка: ${error.message}</div>`;
    }
});

async function deleteGroup(id) {
    if (!confirm('Удалить группу?')) return;

    try {
        await fetch(`/api/admin/groups/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        loadGroups();
    } catch (error) {
        alert('Ошибка удаления группы');
    }
}

// ============ ДИСЦИПЛИНЫ ============

async function loadDisciplines() {
    try {
        const disciplines = await apiRequest('/api/disciplines');
        const container = document.getElementById('disciplinesList');

        if (!disciplines || disciplines.length === 0) {
            container.innerHTML = '<p style="text-align: center; color: #999; padding: 20px;">Дисциплин пока нет</p>';
            return;
        }

        container.innerHTML = disciplines.map(d => `
            <div class="list-item">
                <strong>${d.name}</strong>
                <button class="btn btn-danger" onclick="deleteDiscipline(${d.id})">Удалить</button>
            </div>
        `).join('');
    } catch (error) {
        console.error('Ошибка загрузки дисциплин:', error);
    }
}

function openDisciplineModal() {
    document.getElementById('disciplineModal').classList.add('active');
}

document.getElementById('disciplineForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const alertDiv = document.getElementById('disciplineAlert');

    try {
        const formData = new URLSearchParams();
        formData.append('name', document.getElementById('disciplineName').value);

        await fetch('/api/admin/disciplines', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': `Bearer ${token}`
            },
            body: formData
        });

        alertDiv.innerHTML = '<div class="alert alert-success">Дисциплина успешно добавлена!</div>';
        document.getElementById('disciplineForm').reset();
        setTimeout(() => {
            closeModal('disciplineModal');
            loadDisciplines();
        }, 1500);
    } catch (error) {
        alertDiv.innerHTML = `<div class="alert alert-error">Ошибка: ${error.message}</div>`;
    }
});

async function deleteDiscipline(id) {


    try {
        await fetch(`/api/admin/disciplines/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        loadDisciplines();
    } catch (error) {
        alert('Ошибка удаления дисциплины');
    }
}
// ============ СЕМЕСТРЫ ============

async function loadSemesters() {
    try {
        const semesters = await apiRequest('/api/semesters');
        const container = document.getElementById('semestersList');

        if (!semesters || semesters.length === 0) {
            container.innerHTML = '<p style="text-align: center; color: #999; padding: 20px;">Семестров пока нет</p>';
            return;
        }

        container.innerHTML = semesters.map(s => `
            <div class="list-item">
                <div>
                    <strong>${s.name}</strong>
                    <div style="font-size: 12px; color: #666; margin-top: 4px;">
                        ${new Date(s.start_date).toLocaleDateString('ru-RU')} - ${new Date(s.end_date).toLocaleDateString('ru-RU')}
                    </div>
                    ${s.is_active ? '<span class="badge badge-green">Активный</span>' : ''}
                </div>
                <div style="display: flex; gap: 10px;">
                    ${!s.is_active ? `<button class="btn btn-success" style="margin: 0; padding: 6px 12px;" onclick="activateSemester(${s.id})">Активировать</button>` : ''}
                    <button class="btn btn-danger" style="margin: 0; padding: 6px 12px;" onclick="deleteSemester(${s.id})">Удалить</button>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Ошибка загрузки семестров:', error);
    }
}

function openSemesterModal() {
    document.getElementById('semesterModal').classList.add('active');
}

document.getElementById('semesterForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const alertDiv = document.getElementById('semesterAlert');

    try {
        const data = {
            name: document.getElementById('semesterName').value,
            start_date: document.getElementById('semesterStartDate').value,
            end_date: document.getElementById('semesterEndDate').value,
            is_active: document.getElementById('semesterIsActive').checked
        };

        await fetch('/api/admin/semesters', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(data)
        });

        alertDiv.innerHTML = '<div class="alert alert-success">Семестр успешно добавлен!</div>';
        document.getElementById('semesterForm').reset();
        setTimeout(() => {
            closeModal('semesterModal');
            loadSemesters();
        }, 1500);
    } catch (error) {
        alertDiv.innerHTML = `<div class="alert alert-error">Ошибка: ${error.message}</div>`;
    }
});

async function activateSemester(id) {
    if (!confirm('Сделать этот семестр активным? Предыдущий активный семестр будет деактивирован.')) return;

    try {
        await fetch(`/api/admin/semesters/${id}/activate`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        loadSemesters();
    } catch (error) {
        alert('Ошибка активации семестра');
    }
}

async function deleteSemester(id) {
    if (!confirm('Удалить семестр? Это также удалит все связанные шаблоны расписания!')) return;

    try {
        await fetch(`/api/admin/semesters/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        loadSemesters();
    } catch (error) {
        alert('Ошибка удаления семестра');
    }
}


// ============ РАСПИСАНИЕ ============

function selectWeek(weekType) {
    currentWeekFilter = weekType;
    document.querySelectorAll('.week-btn').forEach(btn => btn.classList.remove('active'));
    event.target.classList.add('active');
    loadScheduleTemplates();
}

async function loadScheduleTemplates() {
    try {
        const templates = await apiRequest('/api/admin/schedule-templates');
        const grid = document.getElementById('scheduleGrid');

        const days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
        const filtered = templates.filter(t =>
            currentWeekFilter === 'both' ? true :
            t.week_type === 'both' || t.week_type === currentWeekFilter
        );

        let html = '';
        for (let day = 0; day < 6; day++) {
            const dayTemplates = filtered.filter(t => t.day_of_week === day);
            html += `
                <div class="day-column">
                    <div class="day-header">${days[day]}</div>
                    ${dayTemplates.map(t => `
                        <div class="lesson-card">
                            <div class="lesson-time">${t.time_start} - ${t.time_end}</div>
                            <div><strong>${t.discipline}</strong></div>
                            <div>${t.lesson_type} | ${t.classroom}</div>
                            <div style="font-size: 10px; color: #666;">${t.teacher}</div>
                            <div style="font-size: 10px;">
                                <span class="badge badge-purple">${t.week_type === 'both' ? 'Обе' : t.week_type === 'odd' ? 'Нечет' : 'Чет'}</span>
                            </div>
                            <button class="btn btn-danger" style="margin-top: 5px; padding: 4px 8px; font-size: 10px;" 
                                    onclick="deleteTemplate(${t.id})">Удалить</button>
                        </div>
                    `).join('')}
                </div>
            `;
        }

        grid.innerHTML = html || '<p style="grid-column: 1/-1; text-align: center; color: #999;">Расписание пусто</p>';
    } catch (error) {
        console.error('Ошибка загрузки расписания:', error);
    }
}

async function openScheduleModal() {
    // Загружаем данные для селектов
    const [disciplines, groups, teachers] = await Promise.all([
        apiRequest('/api/disciplines'),
        apiRequest('/api/groups'),
        apiRequest('/api/admin/teachers')
    ]);

    document.getElementById('scheduleDiscipline').innerHTML =
        disciplines.map(d => `<option value="${d.id}">${d.name}</option>`).join('');

    document.getElementById('scheduleGroups').innerHTML =
        groups.map(g => `<option value="${g.id}">${g.name}</option>`).join('');

    document.getElementById('scheduleTeacher').innerHTML =
        teachers.map(t => `<option value="${t.id}">${t.full_name}</option>`).join('');

    document.getElementById('scheduleModal').classList.add('active');
}

document.getElementById('scheduleForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const alertDiv = document.getElementById('scheduleAlert');

    try {
        const selectedGroups = Array.from(document.getElementById('scheduleGroups').selectedOptions)
            .map(option => option.value);

        const data = {
            discipline_id: parseInt(document.getElementById('scheduleDiscipline').value),
            teacher_id: parseInt(document.getElementById('scheduleTeacher').value),
            lesson_type: document.getElementById('scheduleType').value,
            classroom: document.getElementById('scheduleClassroom').value,
            day_of_week: parseInt(document.getElementById('scheduleDayOfWeek').value),
            week_type: document.getElementById('scheduleWeekType').value,
            time_start: document.getElementById('scheduleTimeStart').value,
            time_end: document.getElementById('scheduleTimeEnd').value,
            group_ids: selectedGroups.map(id => parseInt(id))
        };

        await fetch('/api/admin/schedule-templates', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(data)
        });

        alertDiv.innerHTML = '<div class="alert alert-success">Занятие добавлено в расписание!</div>';
        document.getElementById('scheduleForm').reset();
        setTimeout(() => {
            closeModal('scheduleModal');
            loadScheduleTemplates();
        }, 1500);
    } catch (error) {
        alertDiv.innerHTML = `<div class="alert alert-error">Ошибка: ${error.message}</div>`;
    }
});

async function deleteTemplate(id) {
    if (!confirm('Удалить занятие из расписания?')) return;

    try {
        await fetch(`/api/admin/schedule-templates/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        loadScheduleTemplates();
    } catch (error) {
        alert('Ошибка удаления занятия');
    }
}

async function generateInstances() {
    if (!confirm('Сгенерировать все занятия на семестр из текущих шаблонов? Это может занять некоторое время.')) return;

    try {
        const result = await fetch('/api/admin/generate-instances', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
        });

        const data = await result.json();
        alert(`Успешно сгенерировано ${data.count} занятий!`);
    } catch (error) {
        alert('Ошибка генерации занятий');
    }
}

// Закрытие модального окна
function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('active');
}

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
    loadUserInfo();
    loadStudents();
});

