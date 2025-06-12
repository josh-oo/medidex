import streamlit as st
import os
from dotenv import load_dotenv
from utils.login import show_login

load_dotenv()

BACKEND_API = os.getenv('BACKEND_API')

st.set_page_config(
    page_title="Meerkat AI",
    page_icon="🤖",
)

st.write("")

st.markdown(
    """
    ### Meerkat AI 
    This is a simple demo app for the AI models we trained to map new reports to their corresponding study (studification).
    
    The system reflects the state of Meerkat's 5th version. For demonstration purposes, only studies and reports that we had in our training/validation set are included
    (23696 reports and 16125 studies).

    **👈 This demo app demonstrates two use cases which can be found in the tabs on the left side** 

    However, remember that this is a prototype and things may not yet work as expected.

    ### Assign new reports
    If you get a new report and you want to find the matching studies / Meerkat-tags
    ### Search for studies according to specific tags
    If you want to search Meerkat for studies according to your predefined "tag-based-constraints"
"""
)

with st.sidebar:
    show_login()