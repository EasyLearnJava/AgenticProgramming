# 08 · Vibe-code a data app

A small Streamlit app over a CSV of fruit sales: pick cities and fruits, and see the totals, two charts and the
matching rows. No LangChain and no API key this time. This step is about **how you build**: an AI coding assistant
writes the code from short, clear requests, and you review every change.

```text
City: Chennai   Fruit: Mango   ->   Units sold 110 · Sales ₹5,500 · a bar per fruit · a line per day · 4 rows
```

## What you learn

- **Vibe coding:** describe a change in plain words, let the assistant write it, then read it, run it, and keep it or ask again
- **A mini-spec** for each request: the goal, the inputs, and what "done" looks like
- **One change at a time**, so each change is small enough to review
- **Streamlit:** a Python script becomes a web page, with no HTML and no API routes
- **pandas:** read a CSV, filter rows, and add up a column per group

## The data: `fruit_sales.csv`

One row per day, city and fruit: 4 days × 3 cities × 3 fruits = 36 rows.

| date | city | fruit | units | price |
|---|---|---|---|---|
| 2026-10-01 | Hyderabad | Apple | 40 | 30 |
| 2026-10-01 | Hyderabad | Banana | 120 | 5 |
| 2026-10-01 | Hyderabad | Mango | 25 | 50 |
| … | Chennai, Bengaluru | … | … | … |

`units` is how many were sold and `price` is rupees per piece (Apple 30, Banana 5, Mango 50). The CSV has no
`sales` column: `data.py` works it out as `units × price` when it loads the file.

## Files

| File | What it is |
|---|---|
| `fruit_sales.csv` | The data |
| `data.py` | Plain functions, no Streamlit: `load_sales()`, `filter_sales()`, `sales_by()`. `python data.py` prints the first rows and the totals per fruit |
| `app.py` | The Streamlit page: filters in the sidebar, two totals, two charts, the table |
| `.streamlit/config.toml` | Skips the email question on the first run and turns off usage statistics |
| `tests/test_data.py` | Tests each function in `data.py`, then runs the whole app with Streamlit's `AppTest` and clicks the filters |
| `requirements.txt` | `streamlit`, `pandas` |
| `requirements-dev.txt` | Adds `pytest` |

## How Streamlit works

```python
cities = st.sidebar.multiselect("City", [...], default=[...])   # draws a box, gives back what is picked
rows = filter_sales(sales, cities, fruits)                        # plain pandas
st.bar_chart(sales_by(rows, "fruit"))                             # draws a chart
```

Streamlit runs `app.py` **from top to bottom on every click**. Each `st.…` call draws the next piece of the page.
When you change a filter, the whole script runs again with the new picks, and the page is redrawn. Two lines in
`app.py` exist because of that:

- `@st.cache_data` on `get_sales()`: the CSV is read once, not again on every click.
- `st.stop()`: when nothing is picked, the run ends after the message, so the charts below are never drawn.

The page is split on purpose: `app.py` only draws, and `data.py` does the work. A function like `filter_sales()`
can be tested with no page at all, and it's a small, separate thing to review.

## The app as four mini-specs

This app breaks down into four small requests to a coding assistant. Each one has a goal, the inputs, and "done
when". To practise, start from just the CSV and send them one at a time, reviewing and running each change before
the next.

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
> instead of empty charts. Done when: Chennai + Mango shows 110 units and ₹5,500, and a test checks it.

**4. Add two charts**
> Goal: a bar chart of sales per fruit and a line chart of sales per day, both following the filters. Add
> `sales_by(df, column)` to `data.py`. Done when: both charts change when a filter changes, and the days are in date
> order.

## Your turn: review, then ask for a change

1. **Review what's here.** For each file, can you say what every line does? If not, ask the assistant to explain
   that line before you go on. That's the main skill in this step.
2. **Write your own mini-spec** and ask for it. Some ideas:
   - "Add a third chart: sales per city."
   - "Add a date range filter, from the first day to the last."
   - "Let me upload my own CSV with `st.file_uploader`, as long as it has the same columns."
3. **Review the change before you keep it:** read the diff, run `python -m pytest`, and open the page. If it's
   wrong, say what's wrong and ask again, rather than fixing it by hand.

## Run it

```bash
cd projects/08-vibecode-data-app
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

python data.py                     # the data and the totals per fruit, in the terminal
python -m pytest                   # 9 tests

streamlit run app.py               # the page (Ctrl+C to stop)
```

With the app running, open:

| On your laptop | In GitHub Codespaces |
|---|---|
| http://localhost:8501 | `https://<codespace-name>-8501.app.github.dev` (port **8501** in the Ports tab) |

Streamlit uses port 8501, not 8000, so it can run while another project's server is still on 8000.

## Next

Part B starts the real LLM work: get a Gemini API key and keep it secret on the server.
