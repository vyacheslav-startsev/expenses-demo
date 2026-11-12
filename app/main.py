from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import db
from app.money import format_rub, parse_amount

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


@app.get("/", response_class=HTMLResponse)
def index(request: Request, month: str | None = None):
    month = check_month(month)
    categories = db.by_category(month)
    top = categories[0][1] if categories else 0
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
            "today": date.today().isoformat(),
        },
    )


@app.post("/expenses")
def create(
    spent_on: str = Form(...),
    amount: str = Form(...),
    category: str = Form(...),
    note: str = Form(""),
):
    try:
        day = date.fromisoformat(spent_on)
        amount_kop = parse_amount(amount)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from None
    if category not in db.CATEGORIES:
        raise HTTPException(status_code=400, detail="Неизвестная категория")
    db.add_expense(day.isoformat(), amount_kop, category, note.strip())
    return RedirectResponse(f"/?month={day:%Y-%m}", status_code=303)


@app.post("/expenses/{expense_id}/delete")
def delete(expense_id: int, month: str = Form(...)):
    db.delete_expense(expense_id)
    return RedirectResponse(f"/?month={check_month(month)}", status_code=303)
