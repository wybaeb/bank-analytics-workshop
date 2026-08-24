# -*- coding: utf-8 -*-
"""Правки к инструменту, полученному от ассистента.

Каждая помечена в коде страницы комментарием ПРАВКА N — на занятии по ним
разбирается, что именно пришлось исправить и почему это не видно без запуска.
"""
import pathlib
import re

п = pathlib.Path('инструмент2.html')
t = п.read_text()

# ── ПРАВКА 1: свёртка по месяцам ────────────────────────────────────────────
свёртка = '''
// ПРАВКА 1. Корреляции считались по всем строкам выгрузки, где перемешаны
// регионы и каналы: коэффициент измерял различия между срезами, а не связь
// показателей. Всё, что касается связи, считается на месячных итогах.
// Правило свёртки: объёмные показатели складываются, ставки и средние —
// усредняются, иначе «средний остаток» превратился бы в сумму средних.
function усредняется(колонка) {
    return /средн|ставка|проц|доля|_на_/i.test(колонка);
}

function сводкаПоМесяцам(data, дополнительныйКлюч) {
    // ПРАВКА 2. Месяц разобран в объект даты, а объекты дат не сравниваются
    // между собой: уникальные месяцы не схлопывались, и сводная по срезу
    // получалась в четыре раза длиннее, чем нужно, с пустыми ячейками.
    // Внутри расчётов месяц всегда строка вида ГГГГ-ММ.
    const числовые = Object.keys(COLUMN_TYPES).filter(c => COLUMN_TYPES[c] === 'number');
    const группы = {};
    data.forEach(строка => {
        const месяц = formatDate(строка['месяц']);
        const ключ = дополнительныйКлюч
            ? месяц + '\\u0000' + строка[дополнительныйКлюч]
            : месяц;
        if (!группы[ключ]) группы[ключ] = [];
        группы[ключ].push(строка);
    });
    return Object.keys(группы).sort().map(ключ => {
        const строки = группы[ключ];
        const итог = {'месяц': formatDate(строки[0]['месяц'])};
        if (дополнительныйКлюч) итог[дополнительныйКлюч] = строки[0][дополнительныйКлюч];
        числовые.forEach(колонка => {
            const значения = строки.map(с => с[колонка]).filter(v => v != null && !isNaN(v));
            const сумма = значения.reduce((a, b) => a + b, 0);
            итог[колонка] = усредняется(колонка) ? сумма / значения.length : сумма;
        });
        return итог;
    });
}

// сводная «месяц × значение среза» по одному показателю
function своднаяПоСрезу(data, срез, показатель) {
    const помесячно = сводкаПоМесяцам(data, срез);
    const значения = [...new Set(помесячно.map(с => с[срез]))].sort();
    const месяцы = [...new Set(помесячно.map(с => с['месяц']))].sort();
    const строки = месяцы.map(месяц => {
        const строка = {'месяц': месяц};
        значения.forEach(зн => {
            const найдено = помесячно.find(с => с['месяц'] === месяц && с[срез] === зн);
            строка[зн] = найдено ? найдено[показатель] : null;
        });
        return строка;
    });
    return {строки: строки, колонки: значения};
}
'''
t = t.replace('// Строим корреляционную матрицу', свёртка + '\n// Строим корреляционную матрицу')

# ── ПРАВКА 2 и 3: режимы матрицы ────────────────────────────────────────────
начало = t.index('function buildCorrelationMatrix(data) {')
конец = t.index('// Рендеринг корреляционной матрицы')
новая_матрица = '''function buildCorrelationMatrix(data) {
    const mode = document.getElementById('corrmodeSelect').value;
    const срезы = Object.keys(COLUMN_TYPES).filter(c => COLUMN_TYPES[c] === 'string');
    const числовые = Object.keys(COLUMN_TYPES).filter(c => COLUMN_TYPES[c] === 'number');
    const наборы = document.getElementById('sliceControls');
    наборы.style.display = mode === 'by_slice' ? 'inline' : 'none';

    if (mode === 'between') {
        const помесячно = сводкаПоМесяцам(data);
        const matrix = computeCorrelationMatrix(помесячно, числовые);
        renderCorrelationMatrix(matrix, числовые, помесячно);
        подписьМатрицы('Связь показателей между собой на месячных итогах: '
            + помесячно.length + ' наблюдений');
    } else {
        // ПРАВКА 3. Режим «по срезам» открывал модальное окно и строил матрицу
        // показателей внутри среза. Нужно другое: как связаны между собой
        // значения одного среза по динамике одного показателя.
        const срез = document.getElementById('sliceSelect').value || срезы[0];
        const показатель = document.getElementById('metricSelect').value || числовые[0];
        const сводная = своднаяПоСрезу(data, срез, показатель);
        const matrix = computeCorrelationMatrix(сводная.строки, сводная.колонки);
        renderCorrelationMatrix(matrix, сводная.колонки, сводная.строки);
        подписьМатрицы('Связь между значениями среза «' + срез + '» по показателю «'
            + показатель + '»: ' + сводная.строки.length + ' месяцев');
    }
}

function подписьМатрицы(текст) {
    document.getElementById('matrixNote').textContent = текст;
}

function заполнитьСписки() {
    const срезы = Object.keys(COLUMN_TYPES).filter(c => COLUMN_TYPES[c] === 'string');
    const числовые = Object.keys(COLUMN_TYPES).filter(c => COLUMN_TYPES[c] === 'number');
    const s = document.getElementById('sliceSelect'), m = document.getElementById('metricSelect');
    s.innerHTML = ''; m.innerHTML = '';
    срезы.forEach(c => s.add(new Option(c, c)));
    числовые.forEach(c => m.add(new Option(c, c)));
    s.onchange = m.onchange = () => buildCorrelationMatrix(DATA);
}

'''
t = t[:начало] + новая_матрица + t[конец:]

# рендер матрицы: цветной фон и клик по свёрнутым данным
t = t.replace('function renderCorrelationMatrix(matrix, cols) {',
              'function renderCorrelationMatrix(matrix, cols, основа) {')
t = t.replace("            cell.addEventListener('click', () => scatterPlot(data, rowCol, col));",
              "            cell.addEventListener('click', () => scatterPlot(основа, rowCol, col));")
t = t.replace('''            cell.className = getCorrelationClass(matrix[ri][ci]);''',
'''            // ПРАВКА 4. Классов было три, и матрица читалась ступеньками.
            // Насыщенность фона теперь пропорциональна силе связи.
            const v = matrix[ri][ci];
            const сила = Math.min(1, Math.abs(v));
            cell.style.background = v >= 0
                ? 'rgba(32,186,114,' + (0.08 + 0.72 * сила) + ')'
                : 'rgba(228,87,46,' + (0.08 + 0.72 * сила) + ')';
            cell.style.color = сила > 0.62 ? '#fff' : '#2E3641';
            cell.style.cursor = 'pointer';''')

# ── ПРАВКА 5: сильнейшие связи по свёртке, с кнопкой ────────────────────────
начало = t.index('function findStrongestCorrelations(data) {')
конец = t.index('// Поиск выбросов')
новые_связи = '''function findStrongestCorrelations(data) {
    // ПРАВКА 5. Список считался по строкам выгрузки и не давал открыть пару.
    const помесячно = сводкаПоМесяцам(data);
    const числовые = Object.keys(COLUMN_TYPES).filter(c => COLUMN_TYPES[c] === 'number');
    const matrix = computeCorrelationMatrix(помесячно, числовые);

    const пары = [];
    for (let i = 0; i < числовые.length; i++) {
        for (let j = i + 1; j < числовые.length; j++) {
            пары.push({a: числовые[i], b: числовые[j], r: matrix[i][j]});
        }
    }
    пары.sort((x, y) => Math.abs(y.r) - Math.abs(x.r));

    const listEl = document.getElementById('strongestCorrelationsList');
    listEl.innerHTML = '';
    пары.slice(0, 7).forEach(пара => {
        const li = document.createElement('li');
        const знак = пара.r > 0 ? 'вместе растут и падают' : 'меняются в разные стороны';
        li.innerHTML = '<b>' + пара.r.toFixed(2) + '</b> — ' + пара.a + ' и ' + пара.b
            + ' <span class="muted">(' + силаСловами(пара.r) + ', ' + знак + ')</span> ';
        const btn = document.createElement('button');
        btn.textContent = 'показать';
        btn.className = 'link-btn';
        btn.onclick = () => scatterPlot(помесячно, пара.a, пара.b);
        li.appendChild(btn);
        listEl.appendChild(li);
    });
}

function силаСловами(r) {
    const a = Math.abs(r);
    if (a >= 0.7) return 'сильная связь';
    if (a >= 0.5) return 'заметная связь';
    if (a >= 0.3) return 'умеренная связь';
    return 'связи практически нет';
}

'''
t = t[:начало] + новые_связи + t[конец:]

# ── ПРАВКА 6: диаграмма рассеяния (в ответе её не было вовсе) ───────────────
начало = t.index('function findStrongestCorrelations(data) {')
конец = начало
новый_scatter = '''// ПРАВКА 6. Клик по ячейке матрицы вызывал scatterPlot, но самой функции
// в ответе не было: в консоли ошибка, под матрицей ничего не появлялось.
function scatterPlot(data, xCol, yCol) {
    const ctx = document.getElementById('scatterPlotContainer');
    ctx.innerHTML = '';
    if (xCol === yCol) return;
    const wrap = document.createElement('div');
    wrap.className = 'plot';
    const chartCanvas = document.createElement('canvas');
    wrap.appendChild(chartCanvas);
    ctx.appendChild(wrap);

    const точки = data.map(row => ({x: row[xCol], y: row[yCol]}))
                      .filter(p => p.x != null && p.y != null && !isNaN(p.x) && !isNaN(p.y));
    const r = pearsonCorrelation(точки.map(p => p.x), точки.map(p => p.y));

    if (CHARTS.scatter) CHARTS.scatter.destroy();
    CHARTS.scatter = new Chart(chartCanvas, {
        type: 'scatter',
        data: {datasets: [{data: точки, backgroundColor: 'rgba(27,127,214,.65)',
                           pointRadius: 5}]},
        options: {
            responsive: true, maintainAspectRatio: false,
            scales: {x: {type: 'linear', title: {display: true, text: xCol}},
                     y: {type: 'linear', title: {display: true, text: yCol}}},
            plugins: {legend: {display: false},
                      title: {display: true,
                              text: xCol + ' и ' + yCol + ': коэффициент ' + r.toFixed(2)}}
        }
    });

    // ПРАВКА 6. Коэффициент выводился числом без единого слова о том,
    // что он означает и чего не означает.
    const пояснение = document.createElement('p');
    пояснение.className = 'muted';
    пояснение.innerHTML = 'Каждая точка — один месяц. <b>' + силаСловами(r)
        + '</b>: коэффициент ' + r.toFixed(2)
        + '. Связь не означает причину: оба показателя могут зависеть от третьего.';
    ctx.appendChild(пояснение);
}

'''
t = t[:начало] + новый_scatter + t[конец:]

# ── ПРАВКА 7: динамика по месяцам с подсветкой выбросов ─────────────────────
начало = t.index('function drawTimeSeriesChart(data) {')
конец = t.index("// Обработчик изменения режима корреляций")
новая_динамика = '''function drawTimeSeriesChart(data) {
    // ПРАВКА 7. График строился по 480 строкам выгрузки: на одну подпись
    // месяца приходилось двадцать точек. Ряд собирается из месячных итогов,
    // а точки-выбросы подсвечиваются — ради них инструмент и открывают.
    const числовые = Object.keys(COLUMN_TYPES).filter(c => COLUMN_TYPES[c] === 'number');
    const срезы = Object.keys(COLUMN_TYPES).filter(c => COLUMN_TYPES[c] === 'string');
    const select = document.getElementById('timeseriesSelect');
    const срезSelect = document.getElementById('tsSliceSelect');
    const значSelect = document.getElementById('tsValueSelect');
    if (!select.options.length) {
        числовые.forEach(c => select.add(new Option(c, c)));
        срезSelect.add(new Option('вся выгрузка', ''));
        срезы.forEach(c => срезSelect.add(new Option('по срезу: ' + c, c)));
    }

    function заполнитьЗначения() {
        const срез = срезSelect.value;
        значSelect.innerHTML = '';
        значSelect.style.display = срез ? 'inline' : 'none';
        if (!срез) return;
        [...new Set(data.map(с => с[срез]))].sort()
            .forEach(v => значSelect.add(new Option(v, v)));
    }

    function перерисовать() {
        const показатель = select.value;
        const срез = срезSelect.value;
        const выбранное = значSelect.value;
        const выборка = срез && выбранное
            ? data.filter(с => с[срез] === выбранное) : data;
        const помесячно = сводкаПоМесяцам(выборка);
        const значения = помесячно.map(с => с[показатель]);
        const границы = границыВыброса(значения);
        const цвета = значения.map(v => (v < границы.низ || v > границы.верх)
            ? '#E4572E' : 'rgba(27,127,214,.9)');
        const радиусы = значения.map(v => (v < границы.низ || v > границы.верх) ? 7 : 3);

        if (CHARTS.timeSeries) CHARTS.timeSeries.destroy();
        CHARTS.timeSeries = new Chart(document.getElementById('timeSeriesChart'), {
            type: 'line',
            data: {
                labels: помесячно.map(с => с['месяц']),
                datasets: [{
                    label: показатель, data: значения, fill: false,
                    borderColor: 'rgba(27,127,214,.9)', tension: 0.2,
                    pointBackgroundColor: цвета, pointBorderColor: цвета,
                    pointRadius: радиусы, pointHoverRadius: 9
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {y: {beginAtZero: true}},
                plugins: {
                    legend: {display: false},
                    title: {display: true, text: показатель
                        + (срез && выбранное ? ' · ' + выбранное : ' · вся выгрузка')
                        + ' по месяцам, выбросы выделены'}
                }
            }
        });
    }

    select.onchange = перерисовать;
    срезSelect.onchange = () => { заполнитьЗначения(); перерисовать(); };
    значSelect.onchange = перерисовать;
    заполнитьЗначения();
    перерисовать();
}

function границыВыброса(значения) {
    const чистые = значения.filter(v => v != null && !isNaN(v));
    const q1 = quantile(чистые, 0.25), q3 = quantile(чистые, 0.75);
    const iqr = q3 - q1;
    return {низ: q1 - 1.5 * iqr, верх: q3 + 1.5 * iqr};
}

'''
t = t[:начало] + новая_динамика + t[конец:]

# ── разметка: списки среза и показателя, подпись матрицы, место под scatter ──
t = t.replace('''        <select id="timeseriesSelect"></select>''',
'''        <select id="timeseriesSelect"></select>
        <select id="tsSliceSelect"></select>
        <select id="tsValueSelect" style="display:none"></select>''')

t = t.replace('''        <select id="corrmodeSelect">
            <option value="between">Между показателями</option>
            <option value="by_slice">По срезам</option>
        </select>
        <br/><br/>
        <table class="correlation-matrix" id="correlationMatrix"></table>''',
'''        <select id="corrmodeSelect">
            <option value="between">Между показателями</option>
            <option value="by_slice">По срезам</option>
        </select>
        <span id="sliceControls" style="display:none">
            &nbsp; срез <select id="sliceSelect"></select>
            &nbsp; показатель <select id="metricSelect"></select>
        </span>
        <p class="muted" id="matrixNote"></p>
        <div class="scrollbox">
          <table class="correlation-matrix" id="correlationMatrix"></table>
        </div>
        <p class="muted">Щёлкните по ячейке — под матрицей появится диаграмма
           рассеяния этой пары.</p>
        <div id="scatterPlotContainer"></div>''')

# заполнение списков при загрузке файла
t = t.replace('''function renderDashboard(data) {''',
'''function renderDashboard(data) {
    заполнитьСписки();''')

# стили для кнопки и подписи
t = t.replace('</style>', '''.muted { color: #6B7580; font-size: 14px; }
        .scrollbox { overflow-x: auto; }
        select { margin-right: 8px; }
        .link-btn { background: none; border: 0; color: #1B7FD6; cursor: pointer;
                    text-decoration: underline; padding: 0; font-size: 14px; }
        .correlation-matrix td { text-align: center; font-variant-numeric: tabular-nums; }
        .correlation-matrix th { font-size: 12px; }
    </style>''')

п.write_text(t)
print('патч применён, размер:', len(t))
