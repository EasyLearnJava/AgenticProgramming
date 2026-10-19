"""
RAG step 1: read the knowledge base, a CSV file of 10 IT support articles, with pandas. No AI, no API key.

    data/sample_it_kb.csv  ->  pd.read_csv()  ->  kb, a DataFrame: one row per article, one column per field

Run it in this folder:   python read_kb.py   ->   how many articles, the column names, every article's title,
                                                  system and category, then the first article, column by column
"""
from pathlib import Path

import pandas as pd

# ① The file's path. Path(__file__).resolve().parent is the folder this script is in, and `/` on a Path adds a name
#    to it. A bare "data/sample_it_kb.csv" would be looked for in whatever folder you run the script from.
KB_FILE = Path(__file__).resolve().parent / "data" / "sample_it_kb.csv"

# ② Read the file into a DataFrame, pandas' table: the file's first line gives the column names, and each line
#    after it becomes one row (empty lines are skipped). This is the line that opens and reads the file.
kb = pd.read_csv(KB_FILE)

# ③ to ⑤ print what's in it, but only when this file is run directly (python read_kb.py), not when the tests
#    import it to get `kb`.
if __name__ == "__main__":
    # ③ How many rows (articles) there are, and the column names, in the file's order.
    print(f"{len(kb)} articles")
    print("columns:", kb.columns.tolist())
    print()

    # ④ Three columns of every row, picked by name. to_string() prints every row and column, with nothing cut out.
    print(kb[["title", "system", "category"]].to_string())
    print()

    # ⑤ The first row (iloc[0]: rows are counted from 0), one column per line. :>10 pads each column name to 10
    #    characters, the length of the longest one, "resolution", so the colons line up.
    first = kb.iloc[0]
    for column, value in first.items():
        print(f"{column:>10}: {value}")
