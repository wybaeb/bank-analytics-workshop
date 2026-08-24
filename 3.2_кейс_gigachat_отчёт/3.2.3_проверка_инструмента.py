# -*- coding: utf-8 -*-
"""Приёмка инструмента, полученного от модели: открыть, загрузить, сверить.

Проверка объективная — числа сравниваются с независимым расчётом на pandas,
поэтому итерации промпта можно сравнивать между собой, а не «на глаз».

    python3 проверка_инструмента.py путь_к_файлу.html
"""
import json
import pathlib
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import Select

ВЫГРУЗКА = pathlib.Path('/root/work/sessions/max--76387277381017/'
                        'a360-workspace/data/product/savings_monthly.csv')

# Эталон: посчитан на pandas по месячным итогам (сумма объёмов, среднее ставок).
ЭТАЛОН_ПОКАЗАТЕЛИ = {('закрытые_счета', 'жалобы'): 0.96,
                     ('новые_счета', 'закрытые_счета'): 0.89,
                     ('новые_счета', 'расходы_на_продвижение_тыс_руб'): 0.79,
                     ('новые_счета', 'ставка_по_счёту_проц'): -0.19}
ЭТАЛОН_КАНАЛЫ = {('Мобильное приложение', 'Партнёрская сеть'): 0.97,
                 ('Отделение', 'Сайт банка'): 0.93,
                 ('Мобильное приложение', 'Отделение'): 0.04}
ЭТАЛОН_ВЫБРОСЫ = ['2025-02', '2025-09', '2026-03']


def браузер():
    o = Options()
    for a in ('--headless=new', '--no-sandbox', '--disable-dev-shm-usage',
              '--window-size=1600,3000'):
        o.add_argument(a)
    return webdriver.Chrome(options=o)


def проверить(путь):
    итог = {'файл': str(путь), 'пункты': [], 'ошибки_консоли': []}

    def пункт(имя, ок, деталь=''):
        итог['пункты'].append({'пункт': имя, 'ок': bool(ок), 'деталь': деталь})

    d = браузер()
    try:
        d.get('file://' + str(pathlib.Path(путь).resolve()))
        time.sleep(1)
        поля = d.find_elements('css selector', 'input[type=file]')
        пункт('есть поле загрузки файла', поля)
        if not поля:
            return итог
        поля[0].send_keys(str(ВЫГРУЗКА.resolve()))
        time.sleep(4)

        # страница могла сообщить об ошибке через alert: без этого selenium
        # падает на первом же обращении к документу
        try:
            окно = d.switch_to.alert
            итог['ошибки_консоли'].append('alert: ' + окно.text[:160])
            окно.accept()
            time.sleep(0.5)
        except Exception:
            pass

        консоль = [l['message'][:200] for l in d.get_log('browser')
                   if l['level'] == 'SEVERE']
        итог['ошибки_консоли'] = консоль
        пункт('страница работает без ошибок в консоли', not консоль,
              '; '.join(консоль[:2]))

        текст = d.find_element('tag name', 'body').text
        пункт('паспорт: видно число строк 480', '480' in текст)
        пункт('паспорт: виден период 2024-07 — 2026-06',
              '2024-07' in текст and '2026-06' in текст)

        # ── матрица показателей ────────────────────────────────────────────
        числа = снять_матрицу(d)
        if числа:
            расхождения = []
            for (a, b), эталон in ЭТАЛОН_ПОКАЗАТЕЛИ.items():
                факт = числа.get((a, b), числа.get((b, a)))
                if факт is None or abs(факт - эталон) > 0.03:
                    расхождения.append(f'{a}×{b}: {факт} вместо {эталон}')
            пункт('матрица показателей считается на месячных итогах',
                  not расхождения, '; '.join(расхождения))
        else:
            пункт('матрица показателей считается на месячных итогах', False,
                  'матрица не найдена на странице')

        # ── режим по срезам ────────────────────────────────────────────────
        каналы = переключить_на_срез(d)
        if каналы:
            расхождения = []
            for (a, b), эталон in ЭТАЛОН_КАНАЛЫ.items():
                факт = каналы.get((a, b), каналы.get((b, a)))
                if факт is None or abs(факт - эталон) > 0.04:
                    расхождения.append(f'{a}×{b}: {факт} вместо {эталон}')
            пункт('матрица по срезу «канал» строится верно', not расхождения,
                  '; '.join(расхождения))
        else:
            пункт('матрица по срезу «канал» строится верно', False,
                  'режим по срезам не переключился или матрица пуста')

        # ── выбросы ────────────────────────────────────────────────────────
        текст = d.find_element('tag name', 'body').text
        найдено = [м for м in ЭТАЛОН_ВЫБРОСЫ if м in текст]
        пункт('найдены три заложенные аномалии', len(найдено) == 3,
              f'найдено {len(найдено)} из 3: {найдено}')

        # ── графики ────────────────────────────────────────────────────────
        холсты = d.find_elements('tag name', 'canvas')
        пункт('графики построены', len(холсты) >= 1, f'холстов: {len(холсты)}')
        пункт('нет ошибок после взаимодействия',
              not [l for l in d.get_log('browser') if l['level'] == 'SEVERE'])
    finally:
        d.quit()
    return итог


def снять_матрицу(d):
    """Вытаскивает пары «строка × колонка → коэффициент» из любой таблицы,
    похожей на матрицу: первая строка — заголовки, первая ячейка строки — имя."""
    js = """
    const итог = [];
    document.querySelectorAll('table').forEach(t => {
        const строки = [...t.rows];
        if (строки.length < 3) return;
        const заголовки = [...строки[0].cells].map(c => c.textContent.trim());
        строки.slice(1).forEach(r => {
            const ячейки = [...r.cells].map(c => c.textContent.trim());
            const имя = ячейки[0];
            ячейки.slice(1).forEach((v, i) => {
                const число = parseFloat(v.replace(',', '.'));
                const кол = заголовки[i + 1] !== undefined
                    ? заголовки[i + 1] : заголовки[i];
                if (!isNaN(число) && имя && кол) итог.push([имя, кол, число]);
            });
        });
    });
    return итог;
    """
    try:
        сырое = d.execute_script(js)
    except Exception:
        return {}
    return {(a, b): v for a, b, v in сырое}


def переключить_на_срез(d):
    """Ищет среди select тот, что переключает режим, выбирает срез «канал»."""
    for s in d.find_elements('tag name', 'select'):
        варианты = [o.text.lower() for o in s.find_elements('tag name', 'option')]
        if any('срез' in v or 'канал' in v for v in варианты):
            try:
                Select(s).select_by_index(
                    next(i for i, v in enumerate(варианты)
                         if 'срез' in v or 'канал' in v))
                time.sleep(1.5)
            except Exception:
                continue
    # после переключения могли появиться дополнительные списки
    for s in d.find_elements('tag name', 'select'):
        варианты = [o.text for o in s.find_elements('tag name', 'option')]
        if 'канал' in [v.strip() for v in варианты]:
            try:
                Select(s).select_by_visible_text('канал')
                time.sleep(1.5)
            except Exception:
                pass
    матрица = снять_матрицу(d)
    return {k: v for k, v in матрица.items()
            if 'Мобильное приложение' in k[0] or 'Отделение' in k[0]}


if __name__ == '__main__':
    результат = проверить(sys.argv[1])
    пройдено = sum(1 for п in результат['пункты'] if п['ок'])
    всего = len(результат['пункты'])
    print(f"\n{результат['файл']}: {пройдено} из {всего}\n")
    for п in результат['пункты']:
        знак = '✓' if п['ок'] else '✗'
        print(f"  {знак} {п['пункт']}" + (f" — {п['деталь']}" if п['деталь'] else ''))
    print()
    sys.exit(0 if пройдено == всего else 1)
