
let token = localStorage.getItem('token');
let currentWeekFilter = 'odd';
let studentsPage = 1;
let studentsTotalPages = 1;
const STUDENTS_PAGE_SIZE = 10;
let studentsSearchValue = '';
let studentsGroupFilterValue = '';

let schedulePage = 1;
let scheduleTotalPages = 1;
const SCHEDULE_PAGE_SIZE = 18;
let scheduleFilters = {
    discipline_id: '',
    teacher_id: '',
    group_id: ''
};

let groupsCache = [];
let disciplinesCache = [];
let teachersCache = [];


if (!token) {
    window.location.href = '/login';
}


function logout() {
    localStorage.removeItem('token');
    window.location.href = '/login';
}


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

function populateSelect(selectId, items = [], options = {}) {
    const select = document.getElementById(selectId);
    if (!select) return;

    const {
        placeholder = 'Все',
        valueKey = 'id',
        labelKey = 'name',
        keepEmptyOption = true,
        selectedValue
    } = options;

    const previousValue = select.value;
    let html = '';
    if (keepEmptyOption) {
        html += `<option value="">${placeholder}</option>`;
    }
    html += (items || []).map(item => {
        return `<option value="${item[valueKey]}">${item[labelKey]}</option>`;
    }).join('');
    select.innerHTML = html;

    const targetValue = selectedValue !== undefined ? selectedValue : previousValue;
    if (targetValue !== undefined && targetValue !== null) {
        select.value = targetValue;
    }
}

async function bootstrapFilters() {
    try {
        const [groups, disciplines, teachers] = await Promise.all([
            apiRequest('/api/groups'),
            apiRequest('/api/disciplines'),
            apiRequest('/api/admin/teachers')
        ]);

        groupsCache = groups || [];
        disciplinesCache = disciplines || [];
        teachersCache = teachers || [];

        populateSelect('studentGroupFilter', groupsCache, { placeholder: 'Все группы' });
        populateSelect('scheduleFilterGroup', groupsCache, { placeholder: 'Все группы' });
        populateSelect('reportGroupSelect', groupsCache, { placeholder: 'Выберите группу' });

        populateSelect('scheduleFilterDiscipline', disciplinesCache, { placeholder: 'Все дисциплины' });
        populateSelect('reportDisciplineSelect', disciplinesCache, { placeholder: 'Все дисциплины' });

        populateSelect('scheduleFilterTeacher', teachersCache, { placeholder: 'Все преподаватели', labelKey: 'full_name' });
    } catch (error) {
        console.error('Ошибка загрузки фильтров:', error);
    }
}


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



async function loadStudents(options = {}) {
    const { resetPage = false } = options;
    if (resetPage) {
        studentsPage = 1;
    }

    try {
        const params = new URLSearchParams({
            page: studentsPage,
            page_size: STUDENTS_PAGE_SIZE
        });
        if (studentsSearchValue) params.append('search', studentsSearchValue);
        if (studentsGroupFilterValue) params.append('group_id', studentsGroupFilterValue);

        const response = await apiRequest(`/api/students?${params.toString()}`);
        if (!response) return;

        const meta = response.meta || { page: 1, pages: 1, total: 0 };
        if (meta.pages && studentsPage > meta.pages && meta.total > 0) {
            studentsPage = meta.pages;
            return loadStudents();
        }

        const container = document.getElementById('studentsList');
        const students = response.items || [];

        if (students.length === 0) {
            container.innerHTML = '<p style="text-align: center; color: #999; padding: 20px;">Студенты не найдены</p>';
            updateStudentsPagination(meta);
            return;
        }

        const studentsWithFaceStatus = await Promise.all(
            students.map(async (s) => {
                try {
                    const faceStatus = await apiRequest(`/api/students/${s.id}/has-face`);
                    return { ...s, hasFace: faceStatus.has_face };
                } catch {
                    return { ...s, hasFace: false };
                }
            })
        );

        container.innerHTML = studentsWithFaceStatus.map(s => `
            <div class="list-item">
                <div>
                    <strong>${s.full_name}</strong>
                    <span class="badge badge-blue">${s.group_name || '—'}</span>
                    ${s.hasFace ? '<span class="badge badge-success" title="Фото загружено">[FACE] Фото</span>' : '<span class="badge badge-warning" title="Фото не загружено">Нет фото</span>'}
                    ${s.has_fingerprint ? '<span class="badge badge-success" title="Отпечаток загружен">Отпечаток</span>' : '<span class="badge badge-warning" title="Отпечаток не загружен">Нет отпечатка</span>'}
                </div>
                <div style="display: flex; gap: 10px;">
                    <button class="btn btn-primary" onclick="openUploadFaceModal(${s.id}, '${s.full_name.replace(/'/g, "\\'")}')">
                        ${s.hasFace ? 'Обновить фото' : 'Загрузить фото'}
                    </button>
                    <button class="btn btn-danger" onclick="deleteStudent(${s.id})">Удалить</button>
                </div>
            </div>
        `).join('');

        updateStudentsPagination(meta);
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
            loadStudents({ resetPage: true });
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
        console.log('Ошибка удаления студента');
    }
}

function applyStudentFilters() {
    const searchInput = document.getElementById('studentSearchInput');
    const groupSelect = document.getElementById('studentGroupFilter');
    studentsSearchValue = searchInput ? searchInput.value.trim() : '';
    studentsGroupFilterValue = groupSelect ? groupSelect.value : '';
    loadStudents({ resetPage: true });
}

function resetStudentFilters() {
    const searchInput = document.getElementById('studentSearchInput');
    const groupSelect = document.getElementById('studentGroupFilter');
    if (searchInput) searchInput.value = '';
    if (groupSelect) groupSelect.value = '';
    studentsSearchValue = '';
    studentsGroupFilterValue = '';
    loadStudents({ resetPage: true });
}

function changeStudentsPage(direction) {
    const nextPage = studentsPage + direction;
    if (nextPage < 1 || nextPage > studentsTotalPages) {
        return;
    }
    studentsPage = nextPage;
    loadStudents();
}

function updateStudentsPagination(meta = { page: 1, pages: 1 }) {
    studentsPage = meta.page || 1;
    studentsTotalPages = meta.pages || 1;

    const info = document.getElementById('studentsPageInfo');
    const prevBtn = document.getElementById('studentsPrevBtn');
    const nextBtn = document.getElementById('studentsNextBtn');

    if (info) {
        info.textContent = `Стр. ${studentsPage} из ${studentsTotalPages}`;
    }
    if (prevBtn) {
        prevBtn.disabled = studentsPage <= 1;
    }
    if (nextBtn) {
        nextBtn.disabled = studentsPage >= studentsTotalPages;
    }
}



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
            bootstrapFilters();
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
        bootstrapFilters();
    } catch (error) {
        console.log('Ошибка удаления группы');
    }
}



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
            bootstrapFilters();
        }, 1500);
    } catch (error) {
        alertDiv.innerHTML = `<div class="alert alert-error">Ошибка: ${error.message}</div>`;
    }
});

async function deleteDiscipline(id) {
    if (!confirm('Удалить дисциплину? Это также удалит все связанные расписания!')) return;

    try {
        await fetch(`/api/admin/disciplines/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        loadDisciplines();
        bootstrapFilters();
        toast.success('Дисциплина удалена', 'Готово');
    } catch (error) {
        toast.error('Ошибка удаления дисциплины', 'Ошибка');
    }
}


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
    try {
        await fetch(`/api/admin/semesters/${id}/activate`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        loadSemesters();
    } catch (error) {
        console.log('Ошибка активации семестра');
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
        console.log('Ошибка удаления семестра');
    }
}




function selectWeek(weekType, element) {
    currentWeekFilter = weekType;
    document.querySelectorAll('.week-btn').forEach(btn => btn.classList.remove('active'));
    if (element) {
        element.classList.add('active');
    }
    schedulePage = 1;
    loadScheduleTemplates({ resetPage: true });
}

async function loadScheduleTemplates(options = {}) {
    const { resetPage = false } = options;
    if (resetPage) {
        schedulePage = 1;
    }

    try {
        const params = new URLSearchParams({
            page: schedulePage,
            page_size: SCHEDULE_PAGE_SIZE,
            week_type: currentWeekFilter
        });

        if (scheduleFilters.discipline_id) params.append('discipline_id', scheduleFilters.discipline_id);
        if (scheduleFilters.teacher_id) params.append('teacher_id', scheduleFilters.teacher_id);
        if (scheduleFilters.group_id) params.append('group_id', scheduleFilters.group_id);

        const response = await apiRequest(`/api/admin/schedule-templates?${params.toString()}`);
        if (!response) return;

        const meta = response.meta || { page: 1, pages: 1, total: 0 };
        if (meta.pages && schedulePage > meta.pages && meta.total > 0) {
            schedulePage = meta.pages;
            return loadScheduleTemplates();
        }

        renderScheduleGrid(response.items || []);
        updateSchedulePagination(meta);
    } catch (error) {
        console.error('Ошибка загрузки расписания:', error);
    }
}

function renderScheduleGrid(templates = []) {
    const grid = document.getElementById('scheduleGrid');
    if (!grid) return;

    const days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
    const buckets = Array.from({ length: 6 }, () => []);

    (templates || []).forEach(template => {
        if (template.day_of_week >= 0 && template.day_of_week < buckets.length) {
            buckets[template.day_of_week].push(template);
        }
    });

    let html = '';
    for (let day = 0; day < buckets.length; day++) {
        const dayTemplates = buckets[day];
        dayTemplates.sort((a, b) => a.time_start.localeCompare(b.time_start));
        html += `
            <div class="day-column">
                <div class="day-header">${days[day]}</div>
                ${dayTemplates.length === 0 ? '<div class="empty-day">Нет занятий</div>' : dayTemplates.map(t => `
                    <div class="lesson-card">
                        <div class="lesson-time">${t.time_start} - ${t.time_end}</div>
                        <div><strong>${t.discipline}</strong></div>
                        <div>${t.lesson_type} | ${t.classroom}</div>
                        <div style="font-size: 10px; color: #666;">${t.teacher}</div>
                        <div style="font-size: 10px;">
                            <span class="badge badge-purple">${t.week_type === 'both' ? 'Обе' : t.week_type === 'odd' ? 'Нечет' : 'Чет'}</span>
                        </div>
                        <div style="font-size: 10px; color: #555;">Группы: ${t.groups.map(g => g.name).join(', ')}</div>
                        <button class="btn btn-danger" style="margin-top: 5px; padding: 4px 8px; font-size: 10px;" onclick="deleteTemplate(${t.id})">Удалить</button>
                    </div>
                `).join('')}
            </div>
        `;
    }

    grid.innerHTML = html || '<p style="grid-column: 1/-1; text-align: center; color: #999;">Расписание пусто</p>';
}

function applyScheduleFilters() {
    scheduleFilters.discipline_id = document.getElementById('scheduleFilterDiscipline')?.value || '';
    scheduleFilters.teacher_id = document.getElementById('scheduleFilterTeacher')?.value || '';
    scheduleFilters.group_id = document.getElementById('scheduleFilterGroup')?.value || '';
    loadScheduleTemplates({ resetPage: true });
}

function resetScheduleFilters() {
    const disciplineSelect = document.getElementById('scheduleFilterDiscipline');
    const teacherSelect = document.getElementById('scheduleFilterTeacher');
    const groupSelect = document.getElementById('scheduleFilterGroup');
    if (disciplineSelect) disciplineSelect.value = '';
    if (teacherSelect) teacherSelect.value = '';
    if (groupSelect) groupSelect.value = '';
    scheduleFilters = { discipline_id: '', teacher_id: '', group_id: '' };
    loadScheduleTemplates({ resetPage: true });
}

function changeSchedulePage(direction) {
    const nextPage = schedulePage + direction;
    if (nextPage < 1 || nextPage > scheduleTotalPages) return;
    schedulePage = nextPage;
    loadScheduleTemplates();
}

function updateSchedulePagination(meta = { page: 1, pages: 1 }) {
    schedulePage = meta.page || 1;
    scheduleTotalPages = meta.pages || 1;

    const info = document.getElementById('schedulePageInfo');
    const prevBtn = document.getElementById('schedulePrevBtn');
    const nextBtn = document.getElementById('scheduleNextBtn');

    if (info) {
        info.textContent = `Стр. ${schedulePage} из ${scheduleTotalPages}`;
    }
    if (prevBtn) {
        prevBtn.disabled = schedulePage <= 1;
    }
    if (nextBtn) {
        nextBtn.disabled = schedulePage >= scheduleTotalPages;
    }
}

async function openScheduleModal() {

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
        console.log('Ошибка удаления занятия');
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
        console.log(`Успешно сгенерировано ${data.count} занятий!`);
        loadScheduleTemplates();
    } catch (error) {
        console.log('Ошибка генерации занятий');
    }
}

async function downloadJournalReport(format = null) {
    const groupId = document.getElementById('reportGroupSelect')?.value;
    const dateFrom = document.getElementById('reportDateFrom')?.value;
    const dateTo = document.getElementById('reportDateTo')?.value;
    const disciplineId = document.getElementById('reportDisciplineSelect')?.value;
    const formatSelect = document.getElementById('reportFormatSelect');
    const exportFormat = format || (formatSelect ? formatSelect.value : 'csv');

    if (!groupId || !dateFrom || !dateTo) {
        console.log('Пожалуйста, выберите группу и диапазон дат');
        return;
    }

    const params = new URLSearchParams({
        group_id: groupId,
        date_from: dateFrom,
        date_to: dateTo,
        format: exportFormat
    });
    if (disciplineId) params.append('discipline_id', disciplineId);

    try {
        const response = await fetch(`/api/reports/journal?${params.toString()}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!response.ok) {
            let errorMessage = 'Не удалось сформировать отчёт';
            try {
                const err = await response.json();
                errorMessage = err.detail || errorMessage;
            } catch (_) {  }
            throw new Error(errorMessage);
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const extension = exportFormat === 'xlsx' ? 'xlsx' : exportFormat === 'json' ? 'json' : 'csv';
        const link = document.createElement('a');
        link.href = url;
        link.download = `journal_${dateFrom}_${dateTo}.${extension}`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(url);
    } catch (error) {
        console.log(error.message);
    }
}

async function showSummaryReport() {
    const groupId = document.getElementById('reportGroupSelect')?.value;
    const dateFrom = document.getElementById('reportDateFrom')?.value;
    const dateTo = document.getElementById('reportDateTo')?.value;
    const disciplineId = document.getElementById('reportDisciplineSelect')?.value;

    if (!groupId || !dateFrom || !dateTo) {
        console.log('Пожалуйста, выберите группу и диапазон дат');
        return;
    }

    const params = new URLSearchParams({
        group_id: groupId,
        date_from: dateFrom,
        date_to: dateTo
    });
    if (disciplineId) params.append('discipline_id', disciplineId);

    try {
        const summary = await apiRequest(`/api/reports/summary?${params.toString()}`);
        renderSummaryReport(summary);
    } catch (error) {
        console.error('Ошибка получения сводки:', error);
        console.log('Не удалось получить сводку. Попробуйте позже.');
    }
}

function renderSummaryReport(summary) {
    const container = document.getElementById('summaryReportContainer');
    if (!container) return;

    if (!summary) {
        container.style.display = 'none';
        container.innerHTML = '';
        return;
    }

    const byStatus = summary.attendance?.by_status || {};
    const present = (byStatus.present || 0) + (byStatus.auto_detected || 0) + (byStatus.fingerprint_detected || 0);
    const absent = byStatus.absent || 0;
    const excused = byStatus.excused || 0;
    const missing = byStatus.missing || 0;
    const attendanceRate = summary.attendance?.attendance_rate
        ? `${(summary.attendance.attendance_rate * 100).toFixed(1)}%`
        : '0%';

    const averages = (summary.grades?.student_averages || [])
        .filter(item => item.average_grade !== null)
        .sort((a, b) => (b.average_grade || 0) - (a.average_grade || 0))
        .slice(0, 5);

    container.innerHTML = `
        <p><strong>Группа:</strong> ${summary.group?.name || '-'}</p>
        <p><strong>Период:</strong> ${summary.period?.from || ''} — ${summary.period?.to || ''}</p>
        <div class="summary-grid">
            <div class="summary-item"><span>Занятий</span><strong>${summary.lessons_found || 0}</strong></div>
            <div class="summary-item"><span>Посещаемость</span><strong>${attendanceRate}</strong></div>
            <div class="summary-item"><span>Присутствий</span><strong>${present}</strong></div>
            <div class="summary-item"><span>Отсутствий</span><strong>${absent}</strong></div>
            <div class="summary-item"><span>Уважительно</span><strong>${excused}</strong></div>
            <div class="summary-item"><span>Не отмечено</span><strong>${missing}</strong></div>
            <div class="summary-item"><span>Средний балл</span><strong>${summary.grades?.overall_average ?? '—'}</strong></div>
        </div>
        ${averages.length ? `
            <div style="margin-top: 15px;">
                <strong>Лидеры по успеваемости:</strong>
                <ul style="margin-top: 8px; padding-left: 18px;">
                    ${averages.map(item => `<li>${item.student_name} — ${item.average_grade}</li>`).join('')}
                </ul>
            </div>
        ` : ''}
    `;
    container.style.display = 'block';
}


function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('active');
}



let currentStudentForFaceUpload = null;
let selectedFaceFile = null;

function openUploadFaceModal(studentId, studentName) {
    currentStudentForFaceUpload = studentId;
    document.getElementById('faceStudentName').textContent = studentName;
    document.getElementById('facePreview').style.display = 'none';
    document.getElementById('uploadFaceBtn').disabled = true;
    selectedFaceFile = null;
    document.getElementById('uploadFaceModal').classList.add('active');
}


document.getElementById('faceFileInput').addEventListener('change', function(e) {
    const file = e.target.files[0];
    if (file && file.type.startsWith('image/')) {
        selectedFaceFile = file;


        const reader = new FileReader();
        reader.onload = function(event) {
            const preview = document.getElementById('facePreview');
            preview.src = event.target.result;
            preview.style.display = 'block';
            document.getElementById('uploadFaceBtn').disabled = false;
        };
        reader.readAsDataURL(file);
    } else {
        console.log('Пожалуйста, выберите изображение');
    }
});

async function uploadStudentFace() {
    if (!selectedFaceFile || !currentStudentForFaceUpload) {
        console.log('Выберите фото для загрузки');
        return;
    }

    const btn = document.getElementById('uploadFaceBtn');
    btn.disabled = true;
    btn.textContent = 'Загрузка...';

    try {
        const formData = new FormData();
        formData.append('file', selectedFaceFile);

        const response = await fetch(`/api/students/${currentStudentForFaceUpload}/upload-face`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Ошибка загрузки');
        }

        const result = await response.json();
        console.log(result.message);
        closeModal('uploadFaceModal');
        loadStudents(); 
    } catch (error) {
        console.error('Ошибка загрузки фото:', error);
        console.log('Ошибка: ' + error.message);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Загрузить';
    }
}


document.addEventListener('DOMContentLoaded', async () => {
    loadUserInfo();
    await bootstrapFilters();
    loadStudents({ resetPage: true });

    const searchInput = document.getElementById('studentSearchInput');
    if (searchInput) {
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                applyStudentFilters();
            }
        });
    }

    const groupFilter = document.getElementById('studentGroupFilter');
    if (groupFilter) {
        groupFilter.addEventListener('change', applyStudentFilters);
    }
});

