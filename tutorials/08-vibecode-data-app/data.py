"""
Project 8: the data side of the app. Plain functions, no Streamlit: load the CSV, keep the rows the filters pick,
and add up the sales for a chart. app.py only draws the page; everything here can be tested on its own.

    load_sales()                      ->  every row, plus a `sales` column (units x price)
    filter_sales(df, cities, fruits)  ->  only the rows for those cities and fruits
    sales_by(df, "fruit")             ->  total sales per fruit (or per "date", "city")

Run it on its own:   python data.py   ->   prints the first five rows and the totals per fruit
"""
from pathlib import Path

import pandas as pd

# The CSV next to this file, so it loads the same from any folder.
CSV = Path(__file__).with_name("fruit_sales.csv")


# ① Load: one row per day, city and fruit. `sales` is worked out here, not stored in the CSV: units * price
#    multiplies the two columns for every row at once, with no loop.
#    Dates stay as text like "2026-10-01": text in that shape sorts in date order, which is all the chart needs.
def load_sales(path: Path = CSV) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["sales"] = df["units"] * df["price"]
    return df


# ② Filter: keep a row only if its city AND its fruit were picked.
#    isin() gives one True/False per row. `&` joins two of those row by row (plain `and` fails with "The truth
#    value of a Series is ambiguous"), and df[...] keeps the rows that are True.
def filter_sales(df: pd.DataFrame, cities: list[str], fruits: list[str]) -> pd.DataFrame:
    return df[df["city"].isin(cities) & df["fruit"].isin(fruits)]


# ③ Group: add up the sales for each value of one column, e.g. one total per fruit.
#    groupby() sorts the groups, so the totals per "date" come out in date order.
def sales_by(df: pd.DataFrame, column: str) -> pd.Series:
    return df.groupby(column)["sales"].sum()


# ④ Run it on its own (python data.py), but not when app.py or the tests import it.
if __name__ == "__main__":
    sales = load_sales()
    print(sales.head())
    print()
    print(sales_by(sales, "fruit"))
