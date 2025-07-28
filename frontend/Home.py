import streamlit as st
#import os
from dotenv import load_dotenv
#from utils.login import show_login

load_dotenv()

#page = st.Page("pages/Study.py", title="Study details"),
study_pg = st.Page("pages/study.py", title="Study details", icon=":material/menu_book:"),

pages = {
    "Researchers Panel": [
        st.Page("pages/assign_new_report.py", title="Assign new reports", icon=":material/add_circle:"),
        st.Page("pages/search_studies.py", title="Search studies", icon=":material/search:"),
    ],
    "Admin Panel": [
        st.Page("pages/settings.py", title="Settings", icon=":material/settings:"),
        st.Page("pages/study.py", title="Study details", icon=":material/menu_book:"),
    ],
}

pg = st.navigation(pages, position="hidden")
pg.run()


#with st.sidebar:
#    show_login()