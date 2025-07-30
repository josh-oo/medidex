import streamlit as st
import pandas as pd
import requests
import os
from dotenv import load_dotenv
from utils.login import show_logout, get_headers

import re

load_dotenv()

BACKEND_API = os.getenv('BACKEND_API')

current_batch = None
current_batch_size = None

@st.dialog("Upload new batch")
def add_new_batch():
    uploaded_file = st.file_uploader("Upload your RIS, CGI or NBIB file", type=["ris", "nbib", "cgi"])
    #reason = st.text_input("Because...")
    if st.button("Submit", use_container_width=True, type="primary"):
        if uploaded_file is not None:
            # Read the file content as bytes
            file_content = uploaded_file.getvalue()
            
            # Create a multipart form-data request
            files = {'file': (uploaded_file.name, file_content, 'application/octet-stream')}
            
            # Send the file to FastAPI server for processing
            response = requests.post(BACKEND_API + f"/upload", files=files, headers=get_headers())

            if response.status_code != 200:
                st.error(response.json()['detail'])
            else:
                st.rerun()

@st.dialog("Delete batch")
def delete_batch(batch_hash):
     if st.button("Delete", use_container_width=True, type="primary"):
        response = requests.delete(BACKEND_API + f"/batches/{batch_hash}", headers=get_headers())
        if response.status_code != 200:
            st.error(response.json()['detail'])
        else:
            st.rerun()
         

def visualize_available_batches():
    global current_batch, current_batch_size
    response = requests.get(BACKEND_API + f"/batches", headers=get_headers())

    options = []
    captions=[]
    batch_info = None
    if response.status_code == 200:
        batch_info = response.json()
        for item in batch_info:
            options.append(item['batch_description'])
            captions.append(f" (Loaded {item['embedded']}/{item['number_reports']}; Assigned {item['assigned']}/{item['number_reports']})")

    if len(options) > 0:
        selected_file = st.radio("Start/Continue processing: ", options, captions=captions)
        index = options.index(selected_file)
        current_batch = batch_info[index]['batch_hash']
        current_batch_size = batch_info[index]['number_reports']

    if st.button("Add new batch", use_container_width=True):
        add_new_batch()
    if current_batch is not None:
        if st.button("Delete selected batch", use_container_width=True, type='primary'):
            delete_batch(current_batch)
    
def get_similar_studies(embedding, model, trial_id=None, linked_studies=[]):
    payload = {"model_id": model, "main_embedding": embedding, "author_embedding":None}
    params = {"trial_id": trial_id}
    response = requests.post(BACKEND_API + "/similarity_search/studies", json=payload, params=params, headers=get_headers())

    if response.status_code == 200:
        df = pd.DataFrame(response.json())
        df['Linked'] = [candidate in linked_studies for candidate in df['CRGStudyID']]
        #df['CRGStudyID'] = './study?id=' + df['CRGStudyID'].astype(str) + "&token=" + st.session_state['access_token']
        return df
    else:
        print("Request failed:", response.status_code, response.text)
        return None

def get_similar_tags(embedding, model, sources, tag):
    payload = {"embedding": embedding, "model_id": model}
    params = {"type": tag, "sources": [source.lower() for source in sources]}
    response = requests.post(BACKEND_API + f"/similarity_search/tags", json=payload, headers=get_headers(), params=params)

    if response.status_code == 200:
        return pd.DataFrame(response.json())
    else:
        print("Request failed:", response.status_code, response.text)
        return None
    
def update_selected_studies(selected_studies, current_batch, report_index):
    selected_studies_cleaned = selected_studies

    if len(selected_studies_cleaned) == 0:
        return

    response = requests.put(BACKEND_API + f"/batches/{current_batch}/{report_index}/studies", headers=get_headers(), params={'study_ids': selected_studies_cleaned})
    if response.status_code != 200:
        st.exception(response.text)

@st.cache_data(max_entries=10)
def view_study_details(study_id):
    response = requests.get(BACKEND_API + f"/study/{study_id}/reports", headers=get_headers())

    if response.status_code != 200:
        st.error("Error: " + response.text)
    
    df = pd.DataFrame(response.json())

    file_prefix = "file://///nas.ads.mwn.de/tume/ps0/_AGs/Arbeitsgruppe_Leucht/Meerkat_2020_10_19/PDFs/"
    
    df['PDF'] = file_prefix + df['ReportNumber'].astype(str).str.zfill(5) + ".pdf"

    st.dataframe(df)

def reload_data():
    response = requests.get(BACKEND_API + f"/batches/{current_batch}/{st.session_state['report_index']}", headers=get_headers())
    if response.status_code != 200:
        st.exception(response.text)

    selected_report = response.json()
    st.session_state['selected_report'] = selected_report

    current_model = selected_report['vectors']['model_id']
    current_trial_id = selected_report['trial_id']

    st.session_state['study_search_results'] = get_similar_studies(selected_report['vectors']['embedding'], current_model, trial_id=current_trial_id, linked_studies=selected_report['assigned_studies'])
    st.session_state['intervention_search_results'] = get_similar_tags(selected_report['vectors']['intervention'], current_model, tag_sources, "interventions")
    st.session_state['condition_search_results'] = get_similar_tags(selected_report['vectors']['condition'], current_model, tag_sources,"conditions")
    st.session_state['outcome_search_results'] = get_similar_tags(selected_report['vectors']['outcome'], current_model, tag_sources,"outcomes")

with st.sidebar:
    visualize_available_batches()
    tag_sources = st.multiselect(
        "Sources for tags",
        ["Meerkat", "MeSH"],
        default="Meerkat",
        max_selections=2,
        accept_new_options=False,
    )

if current_batch_size is not None:
    st.number_input("Select a report", value=0, min_value=0, max_value=current_batch_size - 1, step=1, on_change=reload_data, key='report_index')

    if 'selected_report' not in st.session_state:
        reload_data()

    selected_report = st.session_state['selected_report']

    display_title = selected_report['title']
    display_abstract = selected_report['abstract']
    display_authors = selected_report['authors']
    trial_registration_id = selected_report['trial_id']

    if display_title and trial_registration_id and trial_registration_id in display_title:
        display_title = display_title.replace(trial_registration_id, "`" + trial_registration_id + "`")

    if display_abstract and trial_registration_id and trial_registration_id in display_abstract:
        display_abstract= display_abstract.replace(trial_registration_id, "`" + trial_registration_id + "`")

    if display_authors and trial_registration_id:
        for i, author in enumerate(display_authors):
            if trial_registration_id in author:
                display_authors[i] = author.replace(trial_registration_id, "`" + trial_registration_id + "`")

    st.markdown("## " + display_title)
    if display_authors:
        st.markdown(" *and* ".join(display_authors))
    if display_abstract:
        st.markdown(display_abstract)

if 'study_search_results' in st.session_state:
    tab1, tab2, tab3, tab4 = st.tabs(["Studies", "Interventions", "Conditions", "Outcomes"])

    with tab1:
        if 'study_search_results' in st.session_state:
            columns = st.session_state['study_search_results'].columns[:-1]
            new_df = st.data_editor(st.session_state['study_search_results'], hide_index=True, disabled=columns, column_config={ "Linked": st.column_config.CheckboxColumn("Linked",help="Select your the **corresponding** studies", pinned=True, disabled=False)})#, "CRGStudyID": st.column_config.LinkColumn("CRGStudyID", pinned=True, display_text=r"\.\/study\?id=(.+)&token")})
            selected_studies = new_df[new_df['Linked']]['CRGStudyID']
            update_selected_studies(selected_studies, current_batch, st.session_state['report_index'])

            selected_study = st.selectbox("Study details: ", new_df['CRGStudyID'])
            view_study_details(selected_study)
        else:
            st.write("No search results")

    with tab2:
        if 'intervention_search_results' in st.session_state:
            st.dataframe(st.session_state['intervention_search_results'])
        else:
            st.write("No search results")

    with tab3:
        if 'condition_search_results' in st.session_state:
            st.dataframe(st.session_state['condition_search_results'])
        else:
            st.write("No search results")

    with tab4:
        if 'outcome_search_results' in st.session_state:
            st.dataframe(st.session_state['outcome_search_results'])
        else:
            st.write("No search results")