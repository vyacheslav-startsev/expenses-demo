from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import db
from app.money import format_rub, parse_amount
from app.statement import StatementError, parse_statement

BASE = Path(__file__).parent

MONTHS = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Учёт расходов", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")
templates.env.filters["rub"] = format_rub


def shift_month(month: str, delta: int) -> str:
    year, mon = map(int, month.split("-"))
    index = year * 12 + (mon - 1) + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def month_title(month: str) -> str:
    year, mon = map(int, month.split("-"))
    return f"{MONTHS[mon - 1]} {year}"


def check_month(month: str | None) -> str:
    if month is None:
        return date.today().strftime("%Y-%m")
    try:
        year, mon = map(int, month.split("-"))
        date(year, mon, 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Месяц в формате ГГГГ-ММ") from None
    return f"{year:04d}-{mon:02d}"


def render_month(
    request: Request, month: str, *, form: dict | None = None,
    error: str | None = None, status_code: int = 200,
) -> HTMLResponse:
    categories = db.by_category(month)
    top = categories[0][1] if categories else 0
    today = date.today().isoformat()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "month": month,
            "title": month_title(month),
            "prev": shift_month(month, -1),
            "next": shift_month(month, 1),
            "expenses": db.list_month(month),
            "total": db.month_total(month),
            "categories": categories,
            "top": top,
            "all_categories": db.CATEGORIES,
            "form": form or {"spent_on": today},
            "error": error,
        },
        status_code=status_code,
    )


@app.get("/", response_class=HTMLResponse)
def index(request: Request, month: str | None = None):
    return render_month(request, check_month(month))


@app.post("/expenses")
def create(
    request: Request,
    spent_on: str = Form(...),
    amount: str = Form(...),
    category: str = Form(...),
    note: str = Form(""),
):
    day = None
    try:
        try:
            day = date.fromisoformat(spent_on)
        except ValueError:
            raise ValueError("Укажите дату в формате ГГГГ-ММ-ДД") from None
        amount_kop = parse_amount(amount)
        if category not in db.CATEGORIES:
            raise ValueError("Неизвестная категория")
    except ValueError as err:
        month = f"{day:%Y-%m}" if day else check_month(None)
        form = {"spent_on": spent_on, "amount": amount, "category": category, "note": note}
        return render_month(request, month, form=form, error=str(err), status_code=400)
    db.add_expense(day.isoformat(), amount_kop, category, note.strip())
    return RedirectResponse(f"/?month={day:%Y-%m}", status_code=303)


@app.post("/expenses/{expense_id}/delete")
def delete(expense_id: int, month: str = Form(...)):
    db.delete_expense(expense_id)
    return RedirectResponse(f"/?month={check_month(month)}", status_code=303)


@app.post("/import", response_class=HTMLResponse)
async def upload_statement(request: Request, statement: UploadFile):
    try:
        rows = parse_statement(await statement.read())
    except StatementError as err:
        raise HTTPException(status_code=400, detail=str(err)) from None
    known = db.known_refs([r.ref for r in rows if r.skip_reason is None])
    rows = [
        replace(r, skip_reason="уже загружено", selected=False) if r.ref in known else r
        for r in rows
    ]
    return templates.TemplateResponse(
        request,
        "import.html",
        {
            "candidates": [r for r in rows if r.skip_reason is None],
            "skipped": [r for r in rows if r.skip_reason is not None],
            "all_categories": db.CATEGORIES,
        },
    )


@app.post("/import/save")
async def save_statement(request: Request):
    form = await request.form()
    picked = sorted({int(i) for i in form.getlist("pick") if str(i).isdigit()})
    rows = []
    try:
        for i in picked:
            day = date.fromisoformat(str(form[f"spent_on_{i}"]))
            amount_kop = int(str(form[f"amount_kop_{i}"]))
            category = str(form[f"category_{i}"])
            if amount_kop <= 0:
                raise ValueError("Сумма должна быть больше нуля")
            if category not in db.CATEGORIES:
                raise ValueError("Неизвестная категория")
            rows.append((day.isoformat(), amount_kop, category,
                         str(form[f"note_{i}"]).strip(), str(form[f"ref_{i}"])))
    except (KeyError, ValueError) as err:
        raise HTTPException(status_code=400, detail=f"Ошибка в строке импорта: {err}") from None
    if not rows:
        return RedirectResponse("/", status_code=303)
    db.add_imported(rows)
    latest = max(row[0] for row in rows)
    return RedirectResponse(f"/?month={latest[:7]}", status_code=303)
