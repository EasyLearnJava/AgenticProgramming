"""
Tests for project 8: the plain functions in data.py, running data.py as a script, then the whole app, run by
Streamlit's AppTest (no browser needed).

    City: Chennai, Fruit: Mango   ->   the page shows 110 units sold, ₹5,500 and 4 rows

Run them:   python -m pytest        (add -v for one line per test)
"""
import subprocess
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

from data import filter_sales, load_sales, sales_by

FOLDER = Path(__file__).resolve().parent.parent


def test_load_reads_every_row_and_adds_sales():
    sales = load_sales()
    assert len(sales) == 36                        # 4 days x 3 cities x 3 fruits
    assert list(sales.columns) == ["date", "city", "fruit", "units", "price", "sales"]
    first = sales.iloc[0]
    assert (first["city"], first["fruit"], first["units"], first["price"]) == ("Hyderabad", "Apple", 40, 30)
    assert first["sales"] == 40 * 30


def test_filter_keeps_only_the_picked_cities_and_fruits():
    rows = filter_sales(load_sales(), ["Chennai"], ["Mango"])
    assert len(rows) == 4                          # one per day
    assert set(rows["city"]) == {"Chennai"}
    assert set(rows["fruit"]) == {"Mango"}


def test_filter_with_nothing_picked_keeps_nothing():
    assert filter_sales(load_sales(), [], ["Mango"]).empty


def test_sales_by_adds_up_one_total_per_value():
    assert sales_by(load_sales(), "fruit").to_dict() == {"Apple": 15900, "Banana": 7250, "Mango": 16500}


def test_sales_by_date_is_in_date_order():
    per_day = sales_by(load_sales(), "date")
    assert list(per_day.index) == ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]


def test_running_data_py_prints_the_totals():
    result = subprocess.run([sys.executable, str(FOLDER / "data.py")], capture_output=True, text=True, check=True)
    assert "Mango     16500" in result.stdout      # pandas pads each name so the totals line up in a column


def run_app():
    # AppTest gives each run 3 seconds by default. The first run is the slowest (the chart library loads then) and
    # can take longer on a slow or busy machine, so allow 30: a run that finishes sooner doesn't wait.
    return AppTest.from_file(str(FOLDER / "app.py"), default_timeout=30).run()


def test_app_starts_with_every_city_and_fruit_picked():
    app = run_app()
    assert not app.exception
    assert app.title[0].value == "Project 8: Vibe-code a data app"
    city, fruit = app.sidebar.multiselect          # the two multiselects, in the order app.py draws them
    assert city.value == ["Bengaluru", "Chennai", "Hyderabad"]
    assert fruit.value == ["Apple", "Banana", "Mango"]


def test_app_shows_the_totals_for_everything():
    app = run_app()
    assert not app.exception
    assert [m.value for m in app.metric] == ["2,310", "₹39,650"]
    assert app.dataframe[0].value.shape == (36, 6)


def test_app_filters_change_the_totals():
    app = run_app()
    city, fruit = app.sidebar.multiselect          # the two multiselects, in the order app.py draws them
    city.set_value(["Chennai"])
    fruit.set_value(["Mango"])
    app.run()
    assert [m.value for m in app.metric] == ["110", "₹5,500"]
    assert app.dataframe[0].value.shape == (4, 6)


def test_app_says_what_to_do_when_nothing_is_picked():
    app = run_app()
    app.sidebar.multiselect[0].set_value([])
    app.run()
    assert app.info[0].value == "Pick at least one city and one fruit."
    assert len(app.metric) == 0                    # st.stop() ended the run before the totals
