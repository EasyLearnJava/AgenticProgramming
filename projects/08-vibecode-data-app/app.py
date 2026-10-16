"""
Project 8: a small data app. Streamlit turns this script into a web page: pick cities and fruits on the left,
see the totals, two charts and the matching rows.

Run it:   streamlit run app.py   ->   open http://localhost:8501

Streamlit runs this whole file from top to bottom on every click; each st.something() call draws one piece of the
page, in order. The data work lives in data.py.
"""
import streamlit as st

from data import filter_sales, load_sales, sales_by

st.set_page_config(page_title="Fruit sales")     # the browser tab's title
st.title("Fruit sales")


# ① Load the CSV once. Without the cache it would be read again on every click.
@st.cache_data
def get_sales():
    return load_sales()


sales = get_sales()

# ② The filters, in the sidebar. Each multiselect starts with every option picked and gives back a list.
cities = st.sidebar.multiselect("City", sorted(sales["city"].unique()), default=sorted(sales["city"].unique()))
fruits = st.sidebar.multiselect("Fruit", sorted(sales["fruit"].unique()), default=sorted(sales["fruit"].unique()))

rows = filter_sales(sales, cities, fruits)
if rows.empty:
    st.info("Pick at least one city and one fruit.")
    st.stop()                                   # end this run here: nothing below is drawn

# ③ Two totals side by side.
left, right = st.columns(2)
left.metric("Units sold", f"{rows['units'].sum():,}")
right.metric("Sales", f"₹{rows['sales'].sum():,}")

# ④ The two charts: one bar per fruit, one point per day.
st.subheader("Sales per fruit")
st.bar_chart(sales_by(rows, "fruit"))

st.subheader("Sales per day")
st.line_chart(sales_by(rows, "date"))

# ⑤ The rows behind the numbers.
st.subheader(f"The rows ({len(rows)})")
st.dataframe(rows, hide_index=True)
