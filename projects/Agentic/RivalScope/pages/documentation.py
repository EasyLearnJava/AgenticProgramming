"""Render the same user guide that ships with the source code."""

import streamlit as st

from rivalscope.config import ROOT

st.title("RivalScope documentation")
st.markdown((ROOT / "docs" / "USER_GUIDE.md").read_text(encoding="utf-8"))
