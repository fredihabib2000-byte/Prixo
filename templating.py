import os

from fastapi.templating import Jinja2Templates

from config import BASE_DIR

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


def fmt_date(v):
    return v.strftime("%Y-%m-%d") if v else "—"


def fmt_datetime(v):
    return v.strftime("%Y-%m-%d %H:%M") if v else "—"


templates.env.filters["ddate"] = fmt_date
templates.env.filters["dt"] = fmt_datetime
