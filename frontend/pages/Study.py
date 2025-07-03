import streamlit as st
import os
import requests
from dotenv import load_dotenv
import pandas as pd

load_dotenv()

BACKEND_API = os.getenv('BACKEND_API')

def get_reports(study_id, token): 
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(BACKEND_API + f"/study/{study_id}/reports", headers=headers)

    if response.status_code == 200:
        return pd.DataFrame(response.json())
    else:
        st.error("Error: " + response.text)
        return None

if "id" in st.query_params and "token" in st.query_params:
    study_id = st.query_params['id']
    st.header(f"Study {study_id}")

    file_prefix = "file://///nas.ads.mwn.de/tume/ps0/_AGs/Arbeitsgruppe_Leucht/Meerkat_2020_10_19/PDFs/"
    df = get_reports(study_id, st.query_params['token'])
    
    links = file_prefix + df['ReportNumber'].astype(str).str.zfill(5) + ".pdf"
    st.dataframe(df)#, column_config={'ReportNumber': st.column_config.LinkColumn('ReportNumber')})

    #with open("file://////Users/joshua/Desktop/barrowclough-test.pdf", 'rb') as file:
    #    # Display PDF using the embed HTML
    #pdf_display = f'<embed src="file://////Users/joshua/Desktop/barrowclough-test.pdf" width="700" height="900" type="application/pdf">'
    #st.markdown(pdf_display, unsafe_allow_html=True)
    links.name = 'Files'
    st.dataframe(links)

else:
    st.header("No study selected")