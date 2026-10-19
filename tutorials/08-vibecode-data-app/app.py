"""
Project 8: a small data app. Streamlit turns this script into a web page: pick cities and fruits on the left,
see the totals, two charts and the matching rows.

    City: Chennai, Fruit: Mango   ->   Units sold 110, Sales ₹5,500, one bar (Mango), a line through 4 days, 4 rows

Run it:   streamlit run app.py   ->   open http://localhost:8501

Streamlit runs this whole file from top to bottom on every click; each st.something() call draws one piece of the
page, in order. The data work lives in data.py.
"""
import streamlit as st

from data import filter_sales, load_sales, sales_by

st.set_page_config(page_title="Project 8: Vibe-code a data app")     # the browser tab's title
st.title("Project 8: Vibe-code a data app")


# ① Load the CSV once and keep it in memory: without the cache it would be read again on every click.
#    The cache sits here, not in data.py, so data.py stays plain Python that runs without Streamlit.
#    It only notices changes to get_sales() itself: after you edit fruit_sales.csv or load_sales(), stop
#    streamlit (Ctrl+C) and start it again to see them.
@st.cache_data
def get_sales():
    return load_sales()


sales = get_sales()

# ② The filters, in the sidebar. Each multiselect starts with every option picked and gives back a list.
all_cities = sorted(sales["city"].unique())
all_fruits = sorted(sales["fruit"].unique())
cities = st.sidebar.multiselect("City", all_cities, default=all_cities)
fruits = st.sidebar.multiselect("Fruit", all_fruits, default=all_fruits)

rows = filter_sales(sales, cities, fruits)
if rows.empty:
    st.info("Pick at least one city and one fruit.")
    st.stop()                                   # end this run here: nothing below is drawn

# ③ Two totals side by side. The `:,` in each f-string adds thousands commas: 2310 -> "2,310".
left, right = st.columns(2)
left.metric("Units sold", f"{rows['units'].sum():,}")
right.metric("Sales", f"₹{rows['sales'].sum():,}")

# ④ The two charts. Each gets a Series from sales_by(): its index (the fruits, the days) goes along the bottom
#    and its totals up the side, so there's one bar per fruit and one line through the days.
st.subheader("Sales per fruit")
st.bar_chart(sales_by(rows, "fruit"))

st.subheader("Sales per day")
st.line_chart(sales_by(rows, "date"))

# ⑤ The rows behind the numbers. hide_index=True leaves out pandas' row numbers.
st.subheader(f"The rows ({len(rows)})")
st.dataframe(rows, hide_index=True)
