import streamlit as st
import pandas as pd
import requests
import os
from dotenv import load_dotenv
from utils.login import get_headers

load_dotenv()

BACKEND_API = os.getenv('BACKEND_API')

DEFAULT_TOP_K = 10

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
            response = requests.post(BACKEND_API + f"/batches", files=files, headers=get_headers())

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
            st.session_state['selected_report'] = None
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

@st.cache_data(max_entries=1)
def get_similar_studies(embedding, model, trial_id=None, linked_studies=[], k=10):
    payload = {"model_id": model, "main_embedding": embedding, "author_embedding":None}
    params = {"trial_id": trial_id, "k": k}
    response = requests.post(BACKEND_API + "/similarity_search/studies", json=payload, params=params, headers=get_headers())

    if response.status_code == 200:
        df = pd.DataFrame(response.json())
        df['Linked'] = [candidate in linked_studies for candidate in df['CRGStudyID']]
        #df['CRGStudyID'] = './study?id=' + df['CRGStudyID'].astype(str) + "&token=" + st.session_state['access_token']
        return df
    else:
        print("Request failed:", response.status_code, response.text)
        return None

@st.cache_data(max_entries=1)
def get_similar_studies_(batch_hash, report_index, linked_studies=[], k=10):
    params = {"k": k}
    response = requests.get(BACKEND_API + f"/batches/{batch_hash}/{report_index}/similar_studies", params=params, headers=get_headers())

    if response.status_code == 200:
        df = pd.DataFrame(response.json())
        df['Linked'] = [candidate in linked_studies for candidate in df['CRGStudyID']]
        #df['CRGStudyID'] = './study?id=' + df['CRGStudyID'].astype(str) + "&token=" + st.session_state['access_token']
        return df
    else:
        print("Request failed:", response.status_code, response.text)
        return None

@st.cache_data(max_entries=1)
def get_similar_tags(batch_hash, report_index,sources, tag):
    params = {"aspect": tag, "sources": [source.lower() for source in sources]}
    response = requests.get(BACKEND_API + f"/batches/{batch_hash}/{report_index}/similar_tags", headers=get_headers(), params=params)

    if response.status_code == 200:
        return pd.DataFrame(response.json())
    else:
        print("Request failed:", response.status_code, response.text)
        return None
    
def update_selected_studies(selected_studies, current_batch, report_index):

    if selected_studies is None:
        response = requests.delete(BACKEND_API + f"/batches/{current_batch}/{report_index}/studies", headers=get_headers())
        if response.status_code != 200:
            st.exception(response.text)
        return

    if len(selected_studies) == 0:
        return

    response = requests.put(BACKEND_API + f"/batches/{current_batch}/{report_index}/studies", headers=get_headers(), params={'study_ids': selected_studies})
    if response.status_code != 200:
        st.exception(response.text)

@st.cache_data(max_entries=10)
def view_study_details(study_id):
    response = requests.get(BACKEND_API + f"/study/{study_id}/reports", headers=get_headers())

    if response.status_code != 200:
        st.error("Error: " + response.text) 
    
    df = pd.DataFrame(response.json())

    st.dataframe(df, column_config={
        "PDF Links": st.column_config.LinkColumn(
            "PDF Links", display_text="Open PDF"
        ),
    },)

def reload_data():
    response = requests.get(BACKEND_API + f"/batches/{current_batch}/{st.session_state['report_index']}", headers=get_headers())
    if response.status_code != 200:
        st.exception(response.text)

    selected_report = response.json()
    st.session_state['selected_report'] = selected_report
    st.session_state['top_k'] = DEFAULT_TOP_K

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

    st.markdown("### " + display_title)
    if display_authors:
        st.markdown(" *and* ".join(display_authors))
    if display_abstract:
        st.markdown(display_abstract)

if st.session_state.get('selected_report', None):
    selected_report = st.session_state['selected_report']

    tab1, tab2, tab3, tab4 = st.tabs(["Studies", "Interventions", "Conditions", "Outcomes"])

    with tab1:
        #study_search_result = get_similar_studies(selected_report['vectors']['embedding'], selected_report['vectors']['model_id'], trial_id=selected_report['trial_id'], linked_studies=selected_report['assigned_studies'], k=st.session_state['top_k'])
        study_search_result = get_similar_studies_(current_batch, st.session_state['report_index'], linked_studies=selected_report['assigned_studies'], k=st.session_state['top_k'])

        if study_search_result is not None:
            is_new_study = selected_report['assigned_studies'] == [-1]
            columns = study_search_result.columns[:-1]
            new_df = st.data_editor(study_search_result, hide_index=True, disabled=columns, column_config={ "Linked": st.column_config.CheckboxColumn("Linked", pinned=True, disabled=is_new_study), "debug": st.column_config.JsonColumn()})#, "CRGStudyID": st.column_config.LinkColumn("CRGStudyID", pinned=True, display_text=r"\.\/study\?id=(.+)&token")})
            selected_studies = new_df[new_df['Linked']]['CRGStudyID']
            update_selected_studies(selected_studies, current_batch, st.session_state['report_index'])

            if st.button("Load more ...", use_container_width=True):
                st.session_state['top_k'] = st.session_state['top_k'] + DEFAULT_TOP_K
                st.rerun()

            if not is_new_study and st.button("Belongs to a new study", use_container_width=True, type= "secondary"):
                update_selected_studies([-1], current_batch, st.session_state['report_index'])
                selected_report['assigned_studies'] = [-1]
                st.rerun()
            if is_new_study and st.button("Belongs to a new study", use_container_width=True, type= "primary"):
                update_selected_studies(None, current_batch, st.session_state['report_index'])
                selected_report['assigned_studies'] = []
                st.rerun()

            selected_study = st.selectbox("Study details: ", new_df['CRGStudyID'])
            view_study_details(selected_study)
        else:
            st.write("No search results")

    with tab2:
        intervention_search_results = get_similar_tags(current_batch, st.session_state['report_index'], tag_sources, "interventions")
        if intervention_search_results is not None:
            st.dataframe(intervention_search_results)
        else:
            st.write("No search results")

    with tab3:
        condition_search_results = get_similar_tags(current_batch, st.session_state['report_index'], tag_sources, "conditions")
        if condition_search_results is not None:
            st.dataframe(condition_search_results)
        else:
            st.write("No search results")

    with tab4:
        outcome_search_results = get_similar_tags(current_batch, st.session_state['report_index'], tag_sources, "outcomes")
        if outcome_search_results is not None:
            st.dataframe(outcome_search_results)
        else:
            st.write("No search results")