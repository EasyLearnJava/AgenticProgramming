# 08 · Vibe-code a data app

A small Streamlit app over a CSV of fruit sales: pick cities and fruits, and see the totals, two charts and the
matching rows. No LangChain and no API key this time: this step is about **how you build**, with an AI coding
assistant writing the code from short, clear requests while you review every change.

```text
City: Chennai   Fruit: Mango   ->   Units sold 110 · Sales ₹5,500 · one bar (Mango) · a line through 4 days · 4 rows
```

## What you'll build

- `data.py`: three plain pandas functions, `load_sales()`, `filter_sales()` and `sales_by()`. `python data.py` prints
  the first five rows and the total sales per fruit.
- `app.py`: a Streamlit page at http://localhost:8501, with City and Fruit filters in the sidebar, the units sold and
  the sales, a bar chart of sales per fruit, a line chart of sales per day, and the matching rows.
- Tests for the functions on their own, and for the whole page, driven by Streamlit's `AppTest` with no browser.
- [Four mini-specs](#the-app-as-four-mini-specs): the same app as four small requests, to rebuild it with your own
  coding assistant.

## What you'll learn

- **Vibe coding, with review**: describe a change in plain words, let the assistant write it, then read, run and test
  it before you keep it. The term often means accepting the code without reading it; here you read every change.
- **A mini-spec for each request**: the goal, the inputs and what "done" looks like, one small change at a time.
- **Streamlit**: a Python script becomes a web page, with no HTML and no API routes. The whole script runs again
  every time you change a filter, which is why `@st.cache_data` and `st.stop()` are there.
- **pandas**: `read_csv()`, math on whole columns, `isin()` and `&` to keep rows, `groupby()` to add up per group.
- **`AppTest`**: run a Streamlit page inside a test, with no browser.

## What's new since project 07

[Project 07 · Branch and batch a chain](../07-langchain-branch/README.md) served a LangChain chain from FastAPI to a
plain page. Here almost everything around the code changes:

- **No LangChain, FastAPI or `index.html`.** Streamlit draws the page from Python, and `streamlit run app.py` serves
  it on port 8501 instead of `uvicorn main:app` on 8000. Changing a filter reruns the script: there's no `fetch()`
  and no JSON to write.
- **pandas over a CSV instead of a chain.** `data.py` plays `hello.py`'s part (plain functions that the page imports,
  and `python data.py` to try them), and `app.py` takes over from `main.py` and `index.html`.
- **`AppTest` instead of `TestClient`:** the tests run the page itself and change its filters.
- **The lesson is the process:** an AI coding assistant writes the code from mini-specs, and you review each change.

## Before you start

- Python 3.11 or newer (pandas 3.0.6 needs it).
- No API key: that starts in [project 9](../09-gemini-key/README.md).
- For the mini-specs: an AI coding assistant that can read and edit the files in a folder, for example GitHub
  Copilot in VS Code or Codespaces, or Claude Code.

## Files

| File | What it is |
|---|---|
| `fruit_sales.csv` | The data: one row per day, city and fruit, 36 rows |
| `data.py` | Plain functions, no Streamlit: `load_sales()`, `filter_sales()`, `sales_by()`. `python data.py` prints the first five rows and the totals per fruit |
| `app.py` | The Streamlit page: filters in the sidebar, two totals, two charts, the table |
| `.streamlit/config.toml` | Runs Streamlit headless (no email question on the first run, no browser tab opened for you) and turns off usage statistics. Streamlit reads it because it sits next to `app.py` |
| `tests/test_data.py` | Tests each function in `data.py` and `python data.py`, then runs the whole page with Streamlit's `AppTest` and changes the filters |
| `pytest.ini` | Lets the tests `import data` from this folder; only looks in `tests/` |
| `requirements.txt` | `streamlit`, `pandas` |
| `requirements-dev.txt` | Adds `pytest` for the tests |
| `README.md` | This page |

## How it works

### The data: `fruit_sales.csv`

One row per day, city and fruit: 4 days × 3 cities × 3 fruits = 36 rows.

| date | city | fruit | units | price |
|---|---|---|---|---|
| 2026-10-01 | Hyderabad | Apple | 40 | 30 |
| 2026-10-01 | Hyderabad | Banana | 120 | 5 |
| 2026-10-01 | Hyderabad | Mango | 25 | 50 |
| … | Chennai, Bengaluru | … | … | … |

`units` is how many were sold and `price` is rupees per piece (Apple 30, Banana 5, Mango 50). The CSV has no
`sales` column: `data.py` works it out as `units × price` when it loads the file. Altogether that's 2,310 units and
₹39,650.

### `app.py` runs from the top, every time you change a filter

`streamlit run app.py` starts a server that runs the script when you open the page, and **again from the top every
time you change a filter**. Each `st.…` call draws the next piece of the page, in order, so every run redraws the
page with the new picks. The first two lines name the page: the browser tab's title, and the heading.

```python
st.set_page_config(page_title="Project 8: Vibe-code a data app")     # the browser tab's title
st.title("Project 8: Vibe-code a data app")
```

### Load the CSV once: `get_sales()` and `load_sales()`

In `app.py`:

```python
@st.cache_data
def get_sales():
    return load_sales()


sales = get_sales()
```

`@st.cache_data` keeps what `get_sales()` returned the first time and hands it back on every rerun, so the CSV is
read once, not on every click. It wraps `load_sales()` here, in `app.py`, so `data.py` stays plain Python that runs
without Streamlit. The catch: the cache notices changes to `get_sales()` itself, not to the CSV or to
`load_sales()` (see [When things go wrong](#when-things-go-wrong)).

In `data.py`:

```python
CSV = Path(__file__).with_name("fruit_sales.csv")
...
def load_sales(path: Path = CSV) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["sales"] = df["units"] * df["price"]
    return df
```

- `pd.read_csv()` reads the file into a **DataFrame**: a table with named columns. One column, such as
  `df["units"]`, is a **Series**: its 36 values, each with a row label (the **index**, here 0 to 35).
- `df["units"] * df["price"]` multiplies the two columns row by row, all 36 rows at once, with no loop. Assigning it
  to `df["sales"]` adds a sixth column.
- `Path(__file__).with_name(...)` is the CSV next to `data.py`, so it loads the same from any folder.
- The dates stay as text: text like `"2026-10-01"` sorts in date order, which is all the line chart needs.

### Pick cities and fruits: `multiselect` and `filter_sales()`

In `app.py`:

```python
all_cities = sorted(sales["city"].unique())
all_fruits = sorted(sales["fruit"].unique())
cities = st.sidebar.multiselect("City", all_cities, default=all_cities)
fruits = st.sidebar.multiselect("Fruit", all_fruits, default=all_fruits)

rows = filter_sales(sales, cities, fruits)
if rows.empty:
    st.info("Pick at least one city and one fruit.")
    st.stop()                                   # end this run here: nothing below is drawn
```

`unique()` lists each city once and `sorted()` puts them in A-Z order. `st.sidebar.multiselect(...)` draws a box in
the sidebar and gives back what is picked, as a list; the options are also the default, so everything is picked to
start with. If the filters leave no rows, `st.stop()` ends the run after the message, so the totals and charts below
are never drawn.

In `data.py`:

```python
def filter_sales(df: pd.DataFrame, cities: list[str], fruits: list[str]) -> pd.DataFrame:
    return df[df["city"].isin(cities) & df["fruit"].isin(fruits)]
```

- `df["city"].isin(["Chennai"])` gives one True/False per row: `False, False, False, True, True, True, ...` (rows 3
  to 5 are Chennai on the first day).
- `&` joins two of those row by row: True only where the city AND the fruit were picked. Plain `and` doesn't work on
  a Series: it fails with `ValueError: The truth value of a Series is ambiguous`.
- `df[...]` keeps the rows that are True. Chennai + Mango leaves 4 rows, one per day. Nothing picked leaves an empty
  table, which is what `rows.empty` checks.

### The totals: `st.columns` and `metric`

```python
left, right = st.columns(2)
left.metric("Units sold", f"{rows['units'].sum():,}")
right.metric("Sales", f"₹{rows['sales'].sum():,}")
```

`st.columns(2)` makes two columns side by side, and `metric` draws a label over a big number. `.sum()` adds up a
column, and the `:,` in the f-string adds thousands commas: 2310 becomes `"2,310"`.

### The charts: `sales_by()`

In `app.py`:

```python
st.subheader("Sales per fruit")
st.bar_chart(sales_by(rows, "fruit"))

st.subheader("Sales per day")
st.line_chart(sales_by(rows, "date"))
```

In `data.py`:

```python
def sales_by(df: pd.DataFrame, column: str) -> pd.Series:
    return df.groupby(column)["sales"].sum()
```

`groupby(column)` puts the rows into one group per value of that column, and `["sales"].sum()` adds up each group's
sales. The result is a Series with one total per value, sorted by that value, which is what puts the days in date
order:

```text
sales_by(sales, "fruit")  ->  Apple 15900, Banana 7250, Mango 16500
sales_by(sales, "date")   ->  2026-10-01 8450, 2026-10-02 9500, 2026-10-03 10025, 2026-10-04 11675
```

Each chart takes one of those Series: its index (the fruits, or the days) goes along the bottom and its totals up
the side. With everything picked, that's three bars and one line through the four days; with only Mango picked, one
bar.

`python data.py` prints the first five rows, then the totals per fruit:

```text
fruit
Apple     15900
Banana     7250
Mango     16500
Name: sales, dtype: int64
```

### The table, and why there are two files

```python
st.subheader(f"The rows ({len(rows)})")
st.dataframe(rows, hide_index=True)
```

The last step shows the rows behind the numbers, without pandas' row numbers (`hide_index=True`).

The page is split on purpose: `app.py` only draws, and `data.py` does the work. A function like `filter_sales()` can
be tested with no page at all, and each file is a small, separate thing to review. It's the same split as
`hello.py` and `main.py` in projects 02 to 07.

## Run it

```bash
cd projects/08-vibecode-data-app
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell: .venv\Scripts\Activate.ps1
#   Windows Git Bash:   source .venv/Scripts/activate
pip install -r requirements-dev.txt
```

```bash
python data.py                       # the first five rows, then the total sales per fruit
streamlit run app.py                 # the page (Ctrl+C to stop)
```

The terminal says `You can now view your Streamlit app in your browser.` and `Local URL: http://localhost:8501`
(plus a Network URL and an External URL, which you don't need). No browser tab opens by itself, so open the page:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The app | http://localhost:8501 | `https://<codespace-name>-8501.app.github.dev` (port **8501** in the **Ports** tab) |

Streamlit uses port 8501, not 8000, so it can run while another project's server is still on 8000. There's no JSON
API to try with curl this time: the page and Streamlit's server talk over a websocket.

## Test it

```bash
python -m pytest                     # 10 tests
```

10 tests, all plain (no live tests: nothing here calls a model). They take several seconds, and the first app test
is the slowest, because the chart library loads then.

- **6 tests check `data.py` on its own:** 36 rows with a `sales` column, and the first row's sales is 40 × 30;
  Chennai + Mango keeps 4 rows; nothing picked keeps nothing; the totals per fruit are 15900, 7250 and 16500; the
  days come out in date order; and `python data.py` prints Mango's 16500.
- **4 tests run `app.py` with `AppTest`:** the page starts with its title and every city and fruit picked;
  everything picked shows 2,310, ₹39,650 and 36 rows; Chennai + Mango shows 110, ₹5,500 and 4 rows; and no city at
  all shows "Pick at least one city and one fruit." and no totals.

`AppTest` runs `app.py` the way the server would, but with no browser. A test can then read what was drawn, change a
widget and run the script again:

```python
def test_app_filters_change_the_totals():
    app = run_app()
    city, fruit = app.sidebar.multiselect          # the two multiselects, in the order app.py draws them
    city.set_value(["Chennai"])
    fruit.set_value(["Mango"])
    app.run()
    assert [m.value for m in app.metric] == ["110", "₹5,500"]
    assert app.dataframe[0].value.shape == (4, 6)
```

`run_app()` allows each run 30 seconds instead of `AppTest`'s default 3, so a slow or busy machine doesn't fail a
test whose code is fine.

## When things go wrong

| What happens | What you see | What to do |
|---|---|---|
| You edit `fruit_sales.csv` or `load_sales()` while the app runs | The page still shows the old numbers or columns, even after a rerun | `@st.cache_data` is still handing back `get_sales()`'s first result. Stop the app (Ctrl+C) and start it again. On your laptop, the menu at the top right of the page → **Clear cache** works too |
| You run `python app.py` | A hint to run `streamlit run app.py [ARGUMENTS]`, then dozens of `missing ScriptRunContext!` warnings under it, and no page | Start it with `streamlit run app.py` |
| Another Streamlit app (your practice copy, say) is still running | http://localhost:8501 shows the other app, and this app's terminal says `Local URL: http://localhost:8502` | Open the URL the terminal printed, or stop the other app (Ctrl+C) first |
| On Windows, the repo sits in a deep folder | `pip install` stops with `Could not install packages due to an OSError` and a long path inside `site-packages\streamlit\` | Some of Streamlit's files go past Windows' 260-character path limit. Clone the repo into a short folder, such as `C:\code`, and create `.venv` again |

## Things to try

1. **A third chart.** In `app.py`, under the line chart, add `st.subheader("Sales per city")` and
   `st.bar_chart(sales_by(rows, "city"))`, and save. The page shows **File change.** with a **Rerun** button: click
   it. Three bars appear: Bengaluru ₹13,250, Chennai ₹12,500, Hyderabad ₹13,900. `data.py` doesn't change, because
   `sales_by()` takes any column, and the tests still pass.
2. **`and` instead of `&`.** In `filter_sales()`, change the `&` to `and`. Instead of the totals, the page shows
   `ValueError: The truth value of a Series is ambiguous...`, and `python -m pytest` says 6 failed, 4 passed.
   Change it back.
3. **Why `st.stop()` is there.** Delete the `st.stop()` line and unpick every city. Nothing crashes, but under the
   message you get 0, ₹0, two empty charts and "The rows (0)". `python -m pytest` notices: 1 failed, 9 passed.
4. **Start on one city.** Change the City filter's `default=all_cities` to `default=["Chennai"]`. The page opens on
   860 units, ₹12,500 and 12 rows, and `python -m pytest` says 2 failed, 8 passed: two tests still expect
   everything picked at the start. If an assistant made this change without being asked, the tests would catch it.

## The app as four mini-specs

This app breaks down into four small requests to a coding assistant. Each one has a goal, the inputs, and "done
when". To practise, rebuild it from just the CSV: send them one at a time, and review and run each change before
the next.

**Set up a practice folder first.** In this folder your assistant would simply read the finished code, so start in
an empty folder outside the repo, with only the data and the setup files (in bash, or copy the same files by hand):

```bash
mkdir ~/practice-08
cp -r fruit_sales.csv requirements.txt requirements-dev.txt pytest.ini .streamlit ~/practice-08/
cd ~/practice-08                     # this project's .venv can stay active: it has everything the app needs
```

Then open your coding assistant in `~/practice-08` and send it spec 1.

**1. Load the data**
> Goal: a `data.py` with `load_sales()` that reads `fruit_sales.csv` into a pandas DataFrame and adds a `sales`
> column (units × price). Inputs: the CSV next to the file. Done when: `python data.py` prints the first rows with a
> `sales` column, and a test checks 36 rows and that the first row's sales is 40 × 30.

**2. Show it on a page**
> Goal: an `app.py` that shows the total units and total sales side by side, and the rows in a table. Inputs: what
> `load_sales()` returns; read the CSV once, not on every click. Done when: `streamlit run app.py` shows 2,310 units
> and ₹39,650.

**3. Add the filters**
> Goal: a city filter and a fruit filter in the sidebar, everything picked to start with. Put the filtering in
> `data.py` as `filter_sales(df, cities, fruits)`, not in the page. If nothing is picked, show a short message
> instead of zeros and an empty table. Done when: Chennai + Mango shows 110 units and ₹5,500, and a test checks it.

**4. Add two charts**
> Goal: a bar chart of sales per fruit and a line chart of sales per day, both following the filters. Add
> `sales_by(df, column)` to `data.py`. Done when: both charts change when a filter changes, and the days are in date
> order.

**After each spec, review the change before you keep it:**

1. Read it. For each file, can you say what every line does? If not, ask the assistant to explain that line before
   you go on. That's the main skill in this step.
2. Run it: `python -m pytest`, and from spec 2 on, `streamlit run app.py`. Stop this project's app first, or the
   practice app moves to port 8502.
3. If it's wrong, say what's wrong and ask again, rather than fixing it by hand.

**Then write your own fifth mini-spec.** For example:

> Goal: a third total, the average price per piece (total sales ÷ total units), next to the other two. Inputs: the
> rows the filters keep. Done when: it shows ₹17.16 with everything picked, and ₹50.00 for Chennai + Mango.

If it shows ₹28.33, the assistant averaged the `price` column instead: say so, and ask again. That's what "done
when" is for. Other ideas: "Add a date range filter, from the first day to the last" (this will probably change
`load_sales()`, so restart the app to see it), or "Let me upload my own CSV with `st.file_uploader`, as long as it
has the same columns."

## Next

**[Project 09 · Get a Gemini key and keep it secret](../09-gemini-key/README.md)**: create a Gemini API key, cap
what it can spend, and keep it on the server, ready for the first real model call in project 10.
