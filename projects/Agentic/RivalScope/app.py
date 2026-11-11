"""Run with python -m streamlit run app.py from the project directory."""

import streamlit as st

from rivalscope.ui import research_page

st.set_page_config(page_title="RivalScope", page_icon="🔎", layout="wide")

navigation = st.navigation([
    st.Page(research_page, title="Research workspace", icon=":material/search:", default=True),
    st.Page("pages/documentation.py", title="Documentation", icon=":material/menu_book:", url_path="docs"),
])
navigation.run()
