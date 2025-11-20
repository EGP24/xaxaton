const token = localStorage.getItem('token');

if (!token) {
    window.location.href = '/login';
}

const urlParams = new URLSearchParams(window.location.search);
const scheduleId = urlParams.get('schedule_id');
const MIN_GRADE = 2;
const MAX_GRADE = 5;

let selectedPhoto = null;
let scheduleInfo = null;
let allStudents = []; 

function logout() {
    localStorage.removeItem('token');
    window.location.href = '/login';
}

async function apiRequest(url, options = {}) {
    const response = await fetch(url, {
        ...options,
        headers: {
            'Authorization': `Bearer ${token}`,
            ...(options.headers || {})
        }
    });

    if (response.status === 401) {
        logout();
        return null;
    }

    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || 'Ошибка запроса');
    }
    return response.json();
}

async function loadUserInfo() {
    try {
        const user = await apiRequest('/api/me');
        if (user) {
            document.getElementById('teacherName').textContent = `${user.full_name} (${user.role})`;
        }
    } catch (error) {
        console.error(error);
    }
}

async function loadScheduleInfo() {
    if (!scheduleId) return;
    try {
        scheduleInfo = await apiRequest(`/api/schedules/${scheduleId}`);
        const container = document.getElementById('lessonInfo');
        container.innerHTML = `
            <div class="meta-grid">
                <div class="meta-item"><span>Дата</span><strong>${scheduleInfo.date}</strong></div>
                <div class="meta-item"><span>Время</span><strong>${scheduleInfo.time_start} — ${scheduleInfo.time_end}</strong></div>
                <div class="meta-item"><span>Дисциплина</span><strong>${scheduleInfo.discipline}</strong></div>
                <div class="meta-item"><span>Тип</span><strong>${scheduleInfo.lesson_type}</strong></div>
                <div class="meta-item"><span>Аудитория</span><strong>${scheduleInfo.classroom || '—'}</strong></div>
                <div class="meta-item"><span>Группы</span><strong>${scheduleInfo.groups.map(g => g.name).join(', ')}</strong></div>
            </div>
        `;


        const photoSection = document.getElementById('photoUploadSection');
        if (scheduleInfo.is_past && scheduleInfo.can_edit && !scheduleInfo.is_cancelled) {
            photoSection.style.display = 'block';
            initPhotoUpload();
        } else {
            photoSection.style.display = 'none';
        }
    } catch (error) {
        console.error(error);
        document.getElementById('lessonInfo').innerHTML = `<div style="color:#b91c1c;">${error.message}</div>`;
    }
}

async function loadRecords() {
    if (!scheduleId) return;
    const table = document.getElementById('studentsTable');
    try {
        const records = await apiRequest(`/api/schedules/${scheduleId}/records`);
        if (!records || !records.length) {
            table.innerHTML = '<tr><td colspan="4">Студенты не найдены</td></tr>';
            return;
        }


        allStudents = records;

        table.innerHTML = records.map(record => {
            const status = record.status || 'present';
            const grade = record.grade != null ? record.grade : '';
            const isAutoDetected = status === 'auto_detected';
            const isFingerprintDetected = status === 'fingerprint_detected';
            const isPresent = status === 'present' || isAutoDetected || isFingerprintDetected;
            const autoLabel = isFingerprintDetected ? '[О]' : (isAutoDetected ? '[FACE]' : '');
            return `
                <tr data-student-id="${record.student_id}" data-status="${status}">
                    <td>${record.student_name}</td>
                    <td>${record.group_name}</td>
                    <td>
                        <div class="status-buttons">
                            ${renderStatusButton(record.student_id, 'present', 'Присутствовал' + (autoLabel ? ' ' + autoLabel : ''), isPresent, isAutoDetected || isFingerprintDetected)}
                            ${renderStatusButton(record.student_id, 'absent', 'Отсутствовал', status === 'absent')}
                            ${renderStatusButton(record.student_id, 'excused', 'Уважительно', status === 'excused')}
                        </div>
                    </td>
                    <td>
                        <input type="number" min="${MIN_GRADE}" max="${MAX_GRADE}" class="grade-input"
                            value="${grade}" data-student-id="${record.student_id}"
                            onblur="handleGradeChange(${record.student_id})">
                    </td>
                </tr>
            `;
        }).join('');


        updateProgress();
    } catch (error) {
        console.error(error);
        table.innerHTML = `<tr><td colspan="4">${error.message}</td></tr>`;
    }
}

function renderStatusButton(studentId, value, label, active, isAutoDetected = false) {
    const classes = {
        present: 'status-present',
        absent: 'status-absent',
        excused: 'status-excused'
    };
    const aiIndicator = isAutoDetected && value === 'present' ? ' <span class="ai-status-indicator" title="Отмечено автоматически через распознавание лиц">[FACE]</span>' : '';
    return `
        <button class="status-btn ${classes[value]} ${active ? 'active' : ''} ${isAutoDetected ? 'status-auto-detected' : ''}" data-status="${value}"
            onclick="setStatus(${studentId}, '${value}')">${label}${aiIndicator}</button>
    `;
}

async function setStatus(studentId, status) {
    try {
        const gradeInput = document.querySelector(`input.grade-input[data-student-id="${studentId}"]`);
        const gradeValue = gradeInput ? gradeInput.value.trim() : '';
        const grade = gradeValue !== '' ? validateGrade(gradeValue) : null;
        await saveRecord(studentId, status, grade);
        markActiveStatus(studentId, status);


        const studentRow = document.querySelector(`tr[data-student-id="${studentId}"]`);
        const studentName = studentRow ? studentRow.querySelector('td').textContent : 'Студент';
        const statusText = {
            'present': 'Присутствовал',
            'absent': 'Отсутствовал',
            'excused': 'Уважительная причина'
        }[status];

        toast.success(`${studentName}: ${statusText}`, 'Сохранено');
    } catch (error) {
        toast.error(error.message, 'Ошибка сохранения');
    }
}

function markActiveStatus(studentId, status) {
    const row = document.querySelector(`tr[data-student-id="${studentId}"]`);
    if (!row) return;
    row.querySelectorAll('.status-btn').forEach(btn => btn.classList.remove('active'));
    const target = row.querySelector(`.status-btn[data-status="${status}"]`);
    if (target) target.classList.add('active');
}

function getCurrentStatus(studentId) {
    const row = document.querySelector(`tr[data-student-id="${studentId}"]`);
    if (!row) return 'present';
    const active = row.querySelector('.status-btn.active');
    return active?.dataset.status || 'present';
}

function validateGrade(value) {
    if (value === '' || value === null || value === undefined) {
        return null;
    }
    const number = Number(value);
    if (
        Number.isNaN(number) ||
        !Number.isInteger(number) ||
        number < MIN_GRADE ||
        number > MAX_GRADE
    ) {
        throw new Error(`Оценка должна быть целым числом от ${MIN_GRADE} до ${MAX_GRADE}`);
    }
    return number;
}

async function handleGradeChange(studentId) {
    const input = document.querySelector(`input.grade-input[data-student-id="${studentId}"]`);
    if (!input) return;
    try {
        const grade = validateGrade(input.value.trim());
        const status = getCurrentStatus(studentId);
        await saveRecord(studentId, status, grade);


        if (grade !== null) {
            const studentRow = document.querySelector(`tr[data-student-id="${studentId}"]`);
            const studentName = studentRow ? studentRow.querySelector('td').textContent : 'Студент';
            toast.success(`${studentName}: оценка ${grade}`, 'Оценка сохранена');
        }
    } catch (error) {
        toast.error(error.message, 'Ошибка валидации');
        input.value = '';
    }
}

async function saveRecord(studentId, status, grade) {
    const formData = new URLSearchParams();
    formData.append('student_id', studentId);
    formData.append('schedule_id', scheduleId);
    formData.append('status', status || 'present');
    if (grade !== null && grade !== undefined) {
        formData.append('grade', grade);
    }

    const response = await fetch('/api/records', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': `Bearer ${token}`
        },
        body: formData
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || 'Не удалось сохранить запись');
    }
}

function initPhotoUpload() {
    const uploadArea = document.getElementById('photoUploadArea');
    const fileInput = document.getElementById('photoFileInput');
    const preview = document.getElementById('photoPreview');
    const recognizeBtn = document.getElementById('recognizeBtn');
    const clearBtn = document.getElementById('clearPhotoBtn');

    if (!uploadArea || !fileInput) return;

    uploadArea.onclick = () => fileInput.click();

    uploadArea.ondragover = (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragging');
    };

    uploadArea.ondragleave = () => {
        uploadArea.classList.remove('dragging');
    };

    uploadArea.ondrop = (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragging');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handlePhotoSelect(files[0]);
        }
    };

    fileInput.onchange = (e) => {
        if (e.target.files.length > 0) {
            handlePhotoSelect(e.target.files[0]);
        }
    };
}

function handlePhotoSelect(file) {
    if (!file.type.startsWith('image/')) {
        toast.warning('Пожалуйста, выберите изображение', 'Неверный формат');
        return;
    }

    selectedPhoto = file;
    const preview = document.getElementById('photoPreview');
    const recognizeBtn = document.getElementById('recognizeBtn');
    const clearBtn = document.getElementById('clearPhotoBtn');

    const reader = new FileReader();
    reader.onload = (e) => {
        preview.src = e.target.result;
        preview.classList.add('show');
        recognizeBtn.style.display = 'inline-block';
        clearBtn.style.display = 'inline-block';
        toast.info('Фото загружено, нажмите кнопку для распознавания', 'Готово к обработке');
    };
    reader.readAsDataURL(file);
}

function clearPhoto() {
    selectedPhoto = null;
    const preview = document.getElementById('photoPreview');
    const recognizeBtn = document.getElementById('recognizeBtn');
    const clearBtn = document.getElementById('clearPhotoBtn');
    const stats = document.getElementById('recognitionStats');
    const fileInput = document.getElementById('photoFileInput');

    preview.src = '';
    preview.classList.remove('show');
    recognizeBtn.style.display = 'none';
    clearBtn.style.display = 'none';
    stats.classList.remove('show');
    if (fileInput) fileInput.value = '';
}

async function performRecognition() {
    if (!selectedPhoto || !scheduleId) {
        toast.warning('Выберите фото для распознавания', 'Фото не выбрано');
        return;
    }

    const recognizeBtn = document.getElementById('recognizeBtn');
    const stats = document.getElementById('recognitionStats');
    const details = document.getElementById('recognitionDetails');

    recognizeBtn.disabled = true;
    recognizeBtn.textContent = '🔍 Распознавание...';


    toast.info('Обрабатываем фото, это может занять несколько секунд...', 'Распознавание лиц');

    try {
        const formData = new FormData();
        formData.append('file', selectedPhoto);

        const response = await fetch(`/api/schedules/${scheduleId}/recognize-attendance`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            body: formData
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || 'Ошибка при распознавании');
        }

        const result = await response.json();


        details.innerHTML = `
            <div>✅ Распознано: <strong>${result.recognized_count}</strong> из <strong>${result.total_students}</strong> студентов</div>
            <div>👥 Всего лиц на фото: <strong>${result.total_faces}</strong></div>
            <div>📊 Точность: <strong>${result.recognition_rate}</strong></div>
        `;
        stats.classList.add('show');


        await loadRecords();


        const percentage = ((result.recognized_count / result.total_students) * 100).toFixed(0);
        toast.success(
            `Распознано ${result.recognized_count} из ${result.total_students} студентов (${percentage}%)`,
            'Распознавание завершено'
        );
    } catch (error) {
        console.error('Ошибка распознавания:', error);
        toast.error(error.message, 'Ошибка распознавания');
    } finally {
        recognizeBtn.disabled = false;
        recognizeBtn.textContent = '🔍 Распознать и отметить посещаемость';
    }
}



function updateProgress() {
    const rows = document.querySelectorAll('tr[data-student-id]');
    const total = rows.length;
    let marked = 0;

    rows.forEach(row => {
        const status = row.getAttribute('data-status');

        const hasActiveButton = row.querySelector('.status-btn.active');
        if (hasActiveButton) {
            marked++;
        }
    });

    const percentage = total > 0 ? Math.round((marked / total) * 100) : 0;
    const progressEl = document.getElementById('attendanceProgress');

    if (progressEl) {
        progressEl.innerHTML = `${marked} / ${total} <span style="color: #6b7280; font-size: 14px; font-weight: normal;">(${percentage}%)</span>`;
    }
}

async function markAllPresent() {
    if (!allStudents || allStudents.length === 0) {
        toast.warning('Нет студентов для отметки', 'Внимание');
        return;
    }

    if (!confirm(`Отметить всех ${allStudents.length} студентов присутствующими?`)) {
        return;
    }

    toast.info(`Отмечаем ${allStudents.length} студентов...`, 'Обработка');

    let success = 0;
    let errors = 0;

    for (const student of allStudents) {
        try {
            await saveRecord(student.student_id, 'present', null);
            markActiveStatus(student.student_id, 'present');

            const row = document.querySelector(`tr[data-student-id="${student.student_id}"]`);
            if (row) row.setAttribute('data-status', 'present');

            success++;
        } catch (error) {
            console.error(`Ошибка для студента ${student.student_id}:`, error);
            errors++;
        }
    }

    updateProgress();

    if (errors === 0) {
        toast.success(`Все ${success} студентов отмечены присутствующими`, 'Готово');
    } else {
        toast.warning(`Отмечено ${success} из ${allStudents.length}. Ошибок: ${errors}`, 'Завершено с ошибками');
    }
}

async function clearAllMarks() {
    if (!confirm('Очистить все отметки? Это действие нельзя отменить.')) {
        return;
    }


    toast.info('Перезагружаем данные...', 'Очистка');
    await loadRecords();
    toast.success('Отметки сброшены', 'Готово');
}

document.addEventListener('DOMContentLoaded', () => {
    if (!scheduleId) {
        document.getElementById('attendanceBlock').innerHTML = '<div class="meta-card">Не передан идентификатор занятия</div>';
        return;
    }
    loadUserInfo();
    loadScheduleInfo();
    loadRecords();
});

