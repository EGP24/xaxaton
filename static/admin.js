// Основные переменные
let token = localStorage.getItem('token');
let currentGroup = null;
let currentDiscipline = null;
let schedulesByDate = {};

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
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return response.json();
    } catch (error) {
        console.error('API request failed:', error);
        throw error;
    }
}

// Загрузка информации о пользователе
async function loadUserInfo() {
    try {
        const user = await apiRequest('/api/me');
        if (user && user.full_name) {
            document.getElementById('userName').textContent = user.full_name;
            // Показываем кнопку "Панель администратора" только для админов
            if (user.role === 'admin') {
                const adminBtn = document.getElementById('adminPanelBtn');
                if (adminBtn) {
                    adminBtn.style.display = 'block';
                }
            }
        }
    } catch (error) {
        console.error('Ошибка загрузки информации о пользователе:', error);
        logout();
    }
}

// Загрузка списка групп
async function loadGroups() {
    try {
        const groups = await apiRequest('/api/groups');
        if (!groups) return;

        const select = document.getElementById('groupSelect');
        select.innerHTML = '<option value="">Выберите группу</option>';
        groups.forEach(group => {
            const option = document.createElement('option');
            option.value = group.id;
            option.textContent = group.name;
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Ошибка загрузки групп:', error);
        showNoData();
    }
}

// Загрузка дисциплин для группы
async function loadDisciplinesForGroup(groupId) {
    try {
        const schedules = await apiRequest(`/api/schedules?group_id=${groupId}`);
        if (!schedules) {
            showNoData();
            return;
        }

        // Получаем уникальные дисциплины
        const disciplinesMap = new Map();
        schedules.forEach(schedule => {
            if (!disciplinesMap.has(schedule.discipline)) {
                disciplinesMap.set(schedule.discipline, {
                    id: schedule.discipline_id,
                    name: schedule.discipline
                });
            }
        });

        const disciplineSelect = document.getElementById('disciplineSelect');
        disciplineSelect.innerHTML = '<option value="">Выберите дисциплину</option>';
        disciplineSelect.disabled = false;

        disciplinesMap.forEach((discipline, name) => {
            const option = document.createElement('option');
            option.value = name;
            option.textContent = name;
            disciplineSelect.appendChild(option);
        });
    } catch (error) {
        console.error('Ошибка загрузки дисциплин:', error);
        showNoData();
    }
}

// Обработчик изменения группы
document.getElementById('groupSelect').addEventListener('change', async (e) => {
    currentGroup = e.target.value;
    currentDiscipline = null;

    if (currentGroup) {
        await loadDisciplinesForGroup(currentGroup);
    } else {
        document.getElementById('disciplineSelect').disabled = true;
        document.getElementById('disciplineSelect').innerHTML = '<option value="">Сначала выберите группу</option>';
        showNoData();
    }
});

// Обработчик изменения дисциплины
document.getElementById('disciplineSelect').addEventListener('change', async (e) => {
    currentDiscipline = e.target.value;

    if (currentDiscipline && currentGroup) {
        await loadJournal();
    } else {
        showNoData();
    }
});

// Показать сообщение "нет данных"
function showNoData() {
    document.getElementById('loading').style.display = 'none';
    document.getElementById('noData').style.display = 'block';
    document.getElementById('journalTable').style.display = 'none';
}

// Показать загрузку
function showLoading() {
    document.getElementById('loading').style.display = 'block';
    document.getElementById('noData').style.display = 'none';
    document.getElementById('journalTable').style.display = 'none';
}

// Сохранение статуса студента
async function saveRecord(studentId, scheduleId, status, grade = null) {
    try {
        const formData = new URLSearchParams();
        formData.append('student_id', studentId);
        formData.append('schedule_id', scheduleId);
        formData.append('status', status || 'present');
        if (grade !== null && grade !== '') {
            formData.append('grade', grade);
        }

        await fetch('/api/records', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': `Bearer ${token}`
            },
            body: formData
        });
    } catch (error) {
        console.error('Ошибка сохранения записи:', error);
    }
}

// Загрузка журнала
async function loadJournal() {
    showLoading();

    try {
        const schedules = await apiRequest(`/api/schedules?group_id=${currentGroup}`);
        if (!schedules || schedules.length === 0) {
            showNoData();
            return;
        }

        const filteredSchedules = schedules.filter(s => s.discipline === currentDiscipline);

        if (filteredSchedules.length === 0) {
            showNoData();
            return;
        }

        schedulesByDate = {};
        filteredSchedules.forEach(schedule => {
            const date = schedule.date;
            if (!schedulesByDate[date]) {
                schedulesByDate[date] = [];
            }
            schedulesByDate[date].push(schedule);
        });

        const students = await apiRequest(`/api/groups/${currentGroup}/students`);
        if (!students || students.length === 0) {
            showNoData();
            return;
        }

        const recordsPromises = filteredSchedules.map(schedule =>
            apiRequest(`/api/schedules/${schedule.id}/records`)
        );
        const allRecords = await Promise.all(recordsPromises);

        const recordsMap = {};
        allRecords.forEach((records, idx) => {
            if (!records) return;
            const scheduleId = filteredSchedules[idx].id;
            records.forEach(record => {
                const key = `${record.student_id}_${scheduleId}`;
                recordsMap[key] = record;
            });
        });

        buildJournalTable(students, schedulesByDate, recordsMap, filteredSchedules);

        document.getElementById('loading').style.display = 'none';
        document.getElementById('journalTable').style.display = 'table';
    } catch (error) {
        console.error('Ошибка загрузки журнала:', error);
        showNoData();
    }
}

// Построение таблицы журнала
function buildJournalTable(students, schedulesByDate, recordsMap, allSchedules) {
    const tableHead = document.getElementById('tableHead');
    const tableBody = document.getElementById('tableBody');

    const canEditMap = {};
    allSchedules.forEach(schedule => {
        canEditMap[schedule.id] = schedule.can_edit;
    });

    const groupedStudents = {};
    students.forEach(student => {
        const groupName = student.group_name || 'Без группы';
        if (!groupedStudents[groupName]) {
            groupedStudents[groupName] = [];
        }
        groupedStudents[groupName].push(student);
    });

    const sortedDates = Object.keys(schedulesByDate).sort();

    let headerHtml = '<tr><th rowspan="2">Студент</th>';

    sortedDates.forEach(date => {
        const lessonsCount = schedulesByDate[date].length;
        const dateObj = new Date(date + 'T00:00:00');
        const dateStr = dateObj.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
        headerHtml += `<th colspan="${lessonsCount}" class="date-header">${dateStr}</th>`;
    });

    const lessonTypes = new Set();
    Object.values(schedulesByDate).forEach(schedules => {
        schedules.forEach(schedule => lessonTypes.add(schedule.lesson_type));
    });
    const lessonTypesArray = Array.from(lessonTypes).sort();

    headerHtml += `<th colspan="${lessonTypesArray.length + 1}" class="date-header">Средние оценки</th>`;
    headerHtml += '</tr><tr>';

    sortedDates.forEach(date => {
        schedulesByDate[date].forEach(schedule => {
            const lessonType = schedule.lesson_type;
            const time = schedule.time_start;

            let editIcon = '👁️';
            let editText = 'Только просмотр';

            if (schedule.is_cancelled) {
                editIcon = '';
                editText = 'Занятие отменено';
            } else if (!schedule.is_past) {
                editIcon = '';
                editText = 'Будущее занятие - редактирование недоступно';
            } else if (schedule.can_edit) {
                editIcon = '';
                editText = 'Редактирование доступно';
            } else {
                editText = 'Занятие другого преподавателя';
            }

            headerHtml += `<th class="lesson-subheader" title="${schedule.discipline} (${schedule.classroom}) - ${editText}">${lessonType} ${time}</th>`;
        });
    });

    lessonTypesArray.forEach(type => {
        headerHtml += `<th class="lesson-subheader">${type}</th>`;
    });
    headerHtml += `<th class="lesson-subheader">Общая</th>`;
    headerHtml += '</tr>';

    tableHead.innerHTML = headerHtml;

    let bodyHtml = '';

    Object.keys(groupedStudents).sort().forEach(groupName => {
        const groupStudents = groupedStudents[groupName];

        groupStudents.forEach((student, index) => {
            bodyHtml += '<tr>';


            bodyHtml += `<td class="student-name">${student.full_name}</td>`;

            const gradesByType = {};
            lessonTypesArray.forEach(type => gradesByType[type] = []);

            sortedDates.forEach(date => {
                schedulesByDate[date].forEach(schedule => {
                    const key = `${student.id}_${schedule.id}`;
                    const record = recordsMap[key] || { status: null, grade: null };
                    const canEdit = canEditMap[schedule.id];

                    let displayValue = '';
                    let cellClass = '';

                    if (record.grade) {
                        displayValue = record.grade;
                        cellClass = '';
                        if (!gradesByType[schedule.lesson_type]) {
                            gradesByType[schedule.lesson_type] = [];
                        }
                        gradesByType[schedule.lesson_type].push(parseFloat(record.grade));
                    } else if (record.status === 'absent') {
                        displayValue = 'Н';
                        cellClass = 'status-absent';
                    } else if (record.status === 'excused') {
                        displayValue = 'У';
                        cellClass = 'status-excused';
                    }

                    const readonlyAttr = canEdit ? '' : 'readonly';
                    const disabledClass = canEdit ? '' : 'readonly-cell';

                    bodyHtml += `<td class="status-cell ${disabledClass}">
                        <input type="text" 
                               class="status-input ${cellClass}" 
                               value="${displayValue}" 
                               maxlength="4"
                               data-student-id="${student.id}"
                               data-schedule-id="${schedule.id}"
                               data-can-edit="${canEdit}"
                               placeholder="-"
                               ${readonlyAttr}>
                    </td>`;
                });
            });

            let allGrades = [];
            lessonTypesArray.forEach(type => {
                const grades = gradesByType[type] || [];
                if (grades.length > 0) {
                    const avg = grades.reduce((a, b) => a + b, 0) / grades.length;
                    bodyHtml += `<td class="average-cell">${avg.toFixed(2)}</td>`;
                    allGrades.push(...grades);
                } else {
                    bodyHtml += `<td class="average-cell">-</td>`;
                }
            });

            if (allGrades.length > 0) {
                const totalAvg = allGrades.reduce((a, b) => a + b, 0) / allGrades.length;
                bodyHtml += `<td class="average-cell total-average">${totalAvg.toFixed(2)}</td>`;
            } else {
                bodyHtml += `<td class="average-cell total-average">-</td>`;
            }

            bodyHtml += '</tr>';
        });
    });

    tableBody.innerHTML = bodyHtml;
    attachEventHandlers();
}

// Обновление средних оценок для студента
function updateAverages(studentId) {
    const studentRow = document.querySelector(`tr:has(input[data-student-id="${studentId}"])`);
    if (!studentRow) return;

    const inputs = studentRow.querySelectorAll('.status-input');
    const gradesByType = {};

    // Собираем оценки по типам занятий
    inputs.forEach(input => {
        const scheduleId = input.dataset.scheduleId;
        const schedule = Object.values(schedulesByDate).flat().find(s => s.id == scheduleId);
        if (!schedule) return;

        const value = input.value.trim();
        if (value && value !== 'Н' && value !== 'У' && value !== '-') {
            const grade = parseFloat(value.replace(',', '.'));
            if (!isNaN(grade)) {
                if (!gradesByType[schedule.lesson_type]) {
                    gradesByType[schedule.lesson_type] = [];
                }
                gradesByType[schedule.lesson_type].push(grade);
            }
        }
    });

    // Получаем все типы занятий из заголовка
    const lessonTypes = Array.from(document.querySelectorAll('.lesson-subheader'))
        .map(th => th.textContent.trim())
        .filter(text => text && !text.includes(':') && text !== 'Общая');

    // Обновляем ячейки средних оценок
    const averageCells = studentRow.querySelectorAll('.average-cell');
    let allGrades = [];

    lessonTypes.forEach((type, index) => {
        if (averageCells[index]) {
            const grades = gradesByType[type] || [];
            if (grades.length > 0) {
                const avg = grades.reduce((a, b) => a + b, 0) / grades.length;
                averageCells[index].textContent = avg.toFixed(2);
                allGrades.push(...grades);
            } else {
                averageCells[index].textContent = '-';
            }
        }
    });

    // Обновляем общую среднюю
    const totalAvgCell = studentRow.querySelector('.total-average');
    if (totalAvgCell) {
        if (allGrades.length > 0) {
            const totalAvg = allGrades.reduce((a, b) => a + b, 0) / allGrades.length;
            totalAvgCell.textContent = totalAvg.toFixed(2);
        } else {
            totalAvgCell.textContent = '-';
        }
    }
}

// Добавление обработчиков событий для ячеек
function attachEventHandlers() {
    document.querySelectorAll('.status-input').forEach(input => {
        const canEdit = input.dataset.canEdit === 'true';

        if (!canEdit) {
            input.style.cursor = 'not-allowed';
            input.title = 'Только просмотр - это занятие ведет другой преподаватель';
            return;
        }

        input.addEventListener('blur', async (e) => {
            const value = e.target.value.trim();
            const studentId = e.target.dataset.studentId;
            const scheduleId = e.target.dataset.scheduleId;

            let status = null;
            let grade = null;

            if (value === '' || value === '-') {
                status = null;
                grade = null;
            } else if (value === 'Н' || value === 'н') {
                status = 'absent';
                grade = null;
                e.target.value = 'Н';
                e.target.className = 'status-input status-absent';
            } else if (value === 'У' || value === 'у') {
                status = 'excused';
                grade = null;
                e.target.value = 'У';
                e.target.className = 'status-input status-excused';
            } else {
                const numValue = parseFloat(value.replace(',', '.'));
                if (!isNaN(numValue)) {
                    status = null;
                    grade = numValue;
                    e.target.className = 'status-input';
                } else {
                    e.target.value = '';
                    e.target.className = 'status-input';
                    return;
                }
            }

            await saveRecord(studentId, scheduleId, status, grade);
            updateAverages(studentId);
        });

        input.addEventListener('dblclick', async (e) => {
            const currentValue = e.target.value.trim();
            const studentId = e.target.dataset.studentId;
            const scheduleId = e.target.dataset.scheduleId;

            let newValue, status, grade;

            if (currentValue === '' || currentValue === '-' || (!isNaN(parseFloat(currentValue)))) {
                newValue = 'Н';
                status = 'absent';
                grade = null;
                e.target.className = 'status-input status-absent';
            } else if (currentValue === 'Н') {
                newValue = 'У';
                status = 'excused';
                grade = null;
                e.target.className = 'status-input status-excused';
            } else {
                newValue = '';
                status = null;
                grade = null;
                e.target.className = 'status-input';
            }

            e.target.value = newValue;
            await saveRecord(studentId, scheduleId, status, grade);
            updateAverages(studentId);
        });
    });
}

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
    loadUserInfo();
    loadGroups();
    showNoData();
});

