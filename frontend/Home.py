import streamlit as st
#import os
from dotenv import load_dotenv
from utils.login import show_login

load_dotenv()

#page = st.Page("pages/Study.py", title="Study details"),
#study_pg = st.Page("pages/study.py", title="Study details", icon=":material/menu_book:"),

st.set_page_config(
    page_title="Meerkat AI",
    layout="wide"
)

login = st.Page(show_login, title="Login", icon=":material/login:")

assign_new_report = st.Page("pages/assign_new_report.py", title="Assign new reports", icon=":material/add_circle:")
search_studies = st.Page("pages/search_studies.py", title="Search studies", icon=":material/search:")

settings = st.Page("pages/settings.py", title="Settings", icon=":material/settings:")
study = st.Page("pages/study.py", title="Study details", icon=":material/menu_book:")

logged_out_pages = [login]

logged_in_pages = {
    "Researchers Panel": [
        assign_new_report,
        search_studies,
    ],
    "Admin Panel": [
        settings,
        study,
    ],
}

if "access_token" in st.session_state:
    pg = st.navigation(logged_in_pages, position="hidden")
else:
    pg = st.navigation(logged_out_pages, position="hidden")

pg.run()


#with st.sidebar:
#    show_login()