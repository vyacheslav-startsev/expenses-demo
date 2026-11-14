# Импорт банковской выписки — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Загрузка CSV-выписки банка с экраном проверки и сохранением отмеченных операций как расходов без повторов.

**Architecture:** Чистый разборщик `app/statement.py` превращает байты файла в список строк с категорией, галочкой и причиной пропуска. `app/db.py` получает колонку `bank_ref` с уникальным индексом и функции для импорта. Два новых маршрута в `app/main.py` без промежуточного хранения: `POST /import` рендерит страницу проверки, где каждая строка несёт свои данные в скрытых полях, `POST /import/save` записывает отмеченные строки.

**Tech Stack:** Python 3.12, FastAPI (`UploadFile`, `python-multipart` уже в зависимостях), SQLite, Jinja2, pytest. Модуль `csv` из стандартной библиотеки.

**Spec:** `docs/superpowers/specs/2026-11-15-bank-statement-import-design.md`

## Global Constraints

- Формат: UTF-8, BOM допустим, разделитель `;`, дата операции `ДД.ММ.ГГГГ ЧЧ:ММ:СС`, сумма с запятой, расход со знаком минус.
- Дата расхода берётся из «Даты операции», комментарий из «Описания».
- Пропускаются: статус не `OK` («не прошла»), сумма больше нуля («зачисление»), валюта не RUB («не рубли»), ключ уже есть в базе («уже загружено»).
- У категории банка «Переводы» галочка по умолчанию снята, у остальных расходов стоит.
- Ключ операции состоит из времени операции, номера карты, суммы и описания.
- Категории: Супермаркеты → Продукты; Рестораны, Фастфуд → Кафе; Транспорт, Такси → Транспорт; Коммунальные услуги, Связь → Дом; Аптеки → Здоровье; Кино, Цифровые товары → Развлечения; всё остальное → Другое.
- Любая ошибка файла даёт 400 с понятным текстом, и ничего не сохраняется. Так же, как сейчас при ручном вводе (`HTTPException(400, detail=...)`).
- Тексты интерфейса на русском, суммы выводятся фильтром `rub`.
- Новых зависимостей нет.

## Review Focus

1. **Файл пересохранён в Excel в cp1251.** Ожидается 400 «Файл должен быть в UTF-8», а не 500. Тест в Task 1 и Task 3.
2. **BOM в начале и переводы строк CRLF, пустая строка в конце.** Ожидается обычный разбор. Тест в Task 1.
3. **Двойное нажатие «Сохранить» или повторная отправка формы.** Ожидается, что второй раз ничего не добавится. Тест в Task 3.
4. **Подменённые скрытые поля** (неизвестная категория, сумма не число или не больше нуля, кривая дата). Ожидается 400, и ничего не сохраняется, даже из корректных строк той же формы. Тест в Task 3.
5. **Не та таблица** (нет нужной колонки) **или пустой файл.** Ожидается 400 с названием отсутствующей колонки или «Файл пуст». Тест в Task 1.

---

### Task 1: Разбор выписки

**Files:**
- Create: `app/statement.py`
- Test: `tests/test_statement.py`

**Interfaces:**
- Consumes: `app.money.parse_amount(text) -> int` (копейки, только положительные), `app.db.CATEGORIES`.
- Produces:
  ```python
  class StatementError(ValueError): ...

  @dataclass(frozen=True)
  class StatementRow:
      ref: str               # "2026-11-09T13:05:12|*4417|-28000|Кофейня Зерно"
      spent_on: str          # "2026-11-09"
      amount_kop: int        # модуль суммы, > 0
      note: str              # «Описание»
      bank_category: str     # «Категория» как в файле
      category: str          # одна из db.CATEGORIES
      selected: bool         # галочка по умолчанию
      skip_reason: str | None  # None, «не прошла», «зачисление», «не рубли», «уже загружено»

  CATEGORY_MAP: dict[str, str]
  def parse_statement(data: bytes) -> list[StatementRow]
  ```
  Ключ: `f"{datetime.isoformat()}|{карта}|{сумма в копейках со знаком}|{описание}"`. Для зачислений знак `+` не пишется. Строки с `skip_reason` имеют `selected=False`. Порядок строк такой же, как в файле. «Уже загружено» этот модуль не ставит, это делает Task 3.

- [ ] **Step 1: Написать падающие тесты** в `tests/test_statement.py`:
  - `test_parses_sample`: `parse_statement(Path("samples/statement-2026-11.csv").read_bytes())` даёт 24 строки. У строк без `skip_reason` их 22. У отмеченных их 20, а `sum(amount_kop)` равна `3040975`.
  - `test_first_row_fields`: первая строка соответствует `StatementRow(ref="2026-11-11T19:42:10|*4417|-231860|Перекрёсток", spent_on="2026-11-11", amount_kop=231860, note="Перекрёсток", bank_category="Супермаркеты", category="Продукты", selected=True, skip_reason=None)`.
  - `test_skip_reasons`: у строки «Магазин Спортмастерская» причина `"не прошла"`, у «Зачисление заработной платы» причина `"зачисление"`, у строки с валютой `USD` (собранной в тесте) причина `"не рубли"`.
  - `test_transfers_unchecked`: обе строки «Перевод между своими счетами» имеют `skip_reason is None` и `selected is False`, `category == "Другое"`.
  - `test_same_coffee_twice_kept`: две строки «Кофейня Зерно» за 09.11 по 28000 имеют разные `ref`.
  - `test_category_map`: по параметрам проверяются все пары из Global Constraints, а `"Одежда и обувь"` и `"Неизвестное"` дают `"Другое"`.
  - `test_bom_and_crlf`: образец с `b"\xef\xbb\xbf"` в начале, `\r\n` вместо `\n` и пустой строкой в конце разбирается в те же 24 строки.
  - `test_rejects_cp1251`: `sample_text.encode("cp1251")` поднимает `StatementError`, в тексте ошибки есть `"UTF-8"`.
  - `test_rejects_missing_column`: CSV без колонки «Статус» поднимает `StatementError`, в тексте есть `«Статус»`.
  - `test_rejects_empty_and_bad_row`: `b""` даёт `StatementError("Файл пуст")`. Строка с датой `"32.13.2026 25:00:00"` или суммой `"-abc"` даёт `StatementError`, в тексте которого есть номер строки файла.

- [ ] **Step 2: Запустить и убедиться, что тесты падают**
  Run: `uv run pytest tests/test_statement.py -v`
  Expected: FAIL с `ModuleNotFoundError: No module named 'app.statement'`

- [ ] **Step 3: Реализовать `parse_statement(data: bytes) -> list[StatementRow]` в `app/statement.py`.**
  Декодирование через `utf-8-sig`, `UnicodeDecodeError` превращается в `StatementError("Файл должен быть в UTF-8")`. Дальше `csv.DictReader(io.StringIO(text), delimiter=";")`, полностью пустые строки пропускаются. Обязательные колонки: «Дата операции», «Номер карты», «Статус», «Сумма операции», «Валюта операции», «Категория», «Описание». Дата разбирается через `datetime.strptime(s, "%d.%m.%Y %H:%M:%S")`. Сумма: если начинается с `-`, это расход, `parse_amount` от остатка. Иначе это зачисление, его модуль тоже считается через `parse_amount`. Порядок проверки причин пропуска: статус, затем знак, затем валюта. `ValueError` из разбора строки оборачивается в `StatementError(f"Строка {n}: …")`, где `n` — номер строки файла (у заголовка 1).

- [ ] **Step 4: Запустить и убедиться, что тесты проходят**
  Run: `uv run pytest tests/test_statement.py -v`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add app/statement.py tests/test_statement.py
  git commit -m "feat: разбор CSV-выписки банка"
  ```

### Task 2: Ключ операции в базе

**Files:**
- Modify: `app/db.py` (`SCHEMA`, `init_db`, новые функции)
- Test: `tests/test_db_import.py`

**Interfaces:**
- Consumes: ничего из Task 1.
- Produces:
  ```python
  def known_refs(refs: list[str]) -> set[str]          # какие из ключей уже в базе
  def add_imported(rows: list[tuple[str, int, str, str, str]]) -> int
      # (spent_on, amount_kop, category, note, bank_ref); INSERT OR IGNORE; возвращает число добавленных
  ```
  `add_expense` не меняется, у ручных записей `bank_ref` остаётся `NULL`.

- [ ] **Step 1: Написать падающие тесты** в `tests/test_db_import.py` (каждый тест ставит `EXPENSES_DB` на `tmp_path` через `monkeypatch` и вызывает `db.init_db()`):
  - `test_add_imported_skips_known_ref`: `add_imported([("2026-11-09", 28000, "Кафе", "Кофейня Зерно", "r1"), ("2026-11-09", 28000, "Кафе", "Кофейня Зерно", "r2")]) == 2`, повтор того же списка возвращает `0`, а `month_total("2026-11") == 56000`.
  - `test_known_refs`: после вставки `"r1"` выполняется `known_refs(["r1", "r3"]) == {"r1"}`, а `known_refs([]) == set()`.
  - `test_manual_expenses_unaffected`: два `add_expense("2026-11-01", 100, "Кафе")` подряд не конфликтуют, потому что `NULL` не попадает под уникальный индекс.
  - `test_migrates_old_db`: создать базу старой схемой (`CREATE TABLE expenses` без `bank_ref`, плюс одна запись), вызвать `init_db()` дважды. В `PRAGMA table_info(expenses)` появился `bank_ref`, старая запись цела, `add_imported` с ключом работает.

- [ ] **Step 2: Запустить и убедиться, что тесты падают**
  Run: `uv run pytest tests/test_db_import.py -v`
  Expected: FAIL с `AttributeError: module 'app.db' has no attribute 'add_imported'`

- [ ] **Step 3: Реализовать в `app/db.py`.**
  В `SCHEMA` добавляется `bank_ref TEXT`. `init_db` после `CREATE TABLE` проверяет `PRAGMA table_info(expenses)` и, если колонки нет, выполняет `ALTER TABLE expenses ADD COLUMN bank_ref TEXT`. Затем `CREATE UNIQUE INDEX IF NOT EXISTS expenses_bank_ref ON expenses(bank_ref)`. `known_refs` работает через `IN (?, ?, …)`, `add_imported` через `INSERT OR IGNORE` с подсчётом `cur.rowcount`, всё в одной транзакции.

- [ ] **Step 4: Запустить все тесты**
  Run: `uv run pytest -v`
  Expected: PASS, включая старые `tests/test_expenses.py`

- [ ] **Step 5: Commit**
  ```bash
  git add app/db.py tests/test_db_import.py
  git commit -m "feat: ключ банковской операции в таблице расходов"
  ```

### Task 3: Загрузка, экран проверки и сохранение

**Files:**
- Modify: `app/main.py` (два маршрута)
- Create: `app/templates/import.html`
- Modify: `app/templates/index.html` (блок «Загрузить выписку» после «Новый расход»)
- Modify: `app/static/style.css` (стили страницы проверки)
- Modify: `README.md` (раздел «Выписка для импорта»: как загрузить)
- Test: `tests/test_import.py`

**Interfaces:**
- Consumes: `parse_statement`, `StatementError`, `StatementRow` (Task 1), `db.known_refs`, `db.add_imported` (Task 2).
- Produces:
  - `POST /import` с multipart-полем `statement` (файл) возвращает 200 и страницу проверки. Строки, чей `ref` найден в `known_refs`, заменяются через `dataclasses.replace(row, skip_reason="уже загружено", selected=False)`.
  - Форма проверки отправляет на `POST /import/save` поля `count` (число строк-кандидатов), для каждого кандидата `i` поля `ref_{i}`, `spent_on_{i}`, `amount_kop_{i}`, `note_{i}`, `category_{i}` (select), а также чекбокс `pick` со значением `i` (их может быть несколько). Пропущенные строки выводятся отдельным списком без полей.
  - `POST /import/save` отвечает 303 на `/?month=<месяц самой поздней сохранённой операции>`. Если ничего не отмечено, редирект на `/`.

- [ ] **Step 1: Написать падающие тесты** в `tests/test_import.py` (фикстура `client`; хелпер `upload(client, data: bytes)` отправляет `files={"statement": ("s.csv", data, "text/csv")}`, а хелпер `save_form(page_html)` или прямое построение `data` собирает поля сохранения):
  - `test_preview_lists_rows`: загрузка образца даёт 200, на странице есть `"Перекрёсток"`, `"2 318,60 ₽"`, `"не прошла"`, `"зачисление"`, `"Сохранить"`, и `db.month_total("2026-11") == 0`: при просмотре ничего не сохраняется.
  - `test_save_selected`: отправить в `/import/save` все 22 кандидата с отметками как у `selected` из `parse_statement`. Ответ 303 на `/?month=2026-11`, `db.month_total("2026-11") == 3040975`, у категории `"Продукты"` сумма `1295875` (Перекрёсток 2318,60 + 3412,75 + 1867,20 + 1254,90 + 4105,30).
  - `test_category_override_and_unpick`: у одной строки категория меняется на `"Развлечения"`, у другой снимается `pick`. Сохраняется ровно то, что отмечено, и с выбранной категорией.
  - `test_double_save_no_duplicates`: та же форма отправляется дважды, `month_total` не меняется после второго раза.
  - `test_reupload_marks_known`: после сохранения повторная загрузка образца показывает `"уже загружено"` 20 раз.
  - `test_save_rejects_tampered`: при `category_0="Казино"`, или `amount_kop_0="abc"`, или `amount_kop_0="0"`, или `spent_on_0="2026-13-01"` ответ 400, и `month_total == 0`, даже если строка 1 корректна.
  - `test_upload_errors`: при cp1251, пустом файле и CSV без колонки ответ 400, в `response.json()["detail"]` есть текст из `StatementError`.
  - `test_index_has_upload_form`: на `GET /` есть `action="/import"` и `enctype="multipart/form-data"`.

- [ ] **Step 2: Запустить и убедиться, что тесты падают**
  Run: `uv run pytest tests/test_import.py -v`
  Expected: FAIL с 404/405 на `/import`

- [ ] **Step 3: Реализовать маршруты в `app/main.py`.**
  `async def upload(request: Request, statement: UploadFile)` читает `await statement.read()`, `StatementError` превращает в `HTTPException(400, detail=str(err))`, затем отмечает известные ключи. Шаблону передаются `candidates` (строки без `skip_reason`) и `skipped`. `async def save(request: Request)` читает `await request.form()` и сначала проверяет все отмеченные строки: `date.fromisoformat`, `int(...) > 0`, категория в `db.CATEGORIES`, при ошибке 400. Только после этого вызывается один `db.add_imported(...)`.

- [ ] **Step 4: Свёрстать `import.html`, блок загрузки на главной и стили.**
  Страница расширяет `base.html` и использует классы `card`, `list`, `row` и `row-*` из `index.html`. Заголовок «Импорт выписки · N к добавлению, M пропущено». У каждого кандидата есть чекбокс, дата `ДД.ММ`, описание, сумма `|rub` и `<select>` с `all_categories`, где выбрана `row.category`. Ниже идёт список «Пропущено» с причиной и кнопка «Сохранить». На главной выводится карточка «Загрузить выписку»: форма `method="post" action="/import" enctype="multipart/form-data"`, внутри `<input type="file" name="statement" accept=".csv" required>` и кнопка «Загрузить».

- [ ] **Step 5: Запустить все тесты**
  Run: `uv run pytest -v`
  Expected: PASS

- [ ] **Step 6: Проверить в живом приложении**
  Run: `uv run python seed.py && uv run uvicorn app.main:app`. Загрузить `samples/statement-2026-11.csv`, посмотреть экран проверки, сохранить и убедиться, что открылся ноябрь с новыми суммами. Загрузить файл повторно: все строки должны быть помечены «уже загружено». Дубли с seed за 1–6 ноября ожидаемы, это особенность демо-базы (см. дизайн).

- [ ] **Step 7: Обновить README и закоммитить**
  ```bash
  git add app/main.py app/templates/import.html app/templates/index.html app/static/style.css README.md tests/test_import.py
  git commit -m "feat: загрузка выписки с экраном проверки"
  ```
