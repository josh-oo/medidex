import streamlit as st
import pandas as pd
import requests
import os
from dotenv import load_dotenv
from utils.login import show_login, get_headers

load_dotenv()

BACKEND_API = os.getenv('BACKEND_API')

current_embedding = None
current_aspect_embeddings = None
current_model = None

def get_embeddings(text):
    payload = {"text": text}
    response = requests.post(BACKEND_API + "/embed/report", json=payload, headers=get_headers())

    if response.status_code == 200:
        data = response.json()
        embedding = data.pop("embedding")
        model = data.pop("model_id")
        aspect_embeddings = data

        return model, embedding, aspect_embeddings
        
    else:
        print("Request failed:", response.status_code, response.text)
        return None, None, None
    
def get_similar_studies(embedding, model, trial_id=None):
    payload = {"embedding": embedding, "model_id": model}
    params = {"trial_id": trial_id}
    response = requests.post(BACKEND_API + "/similarity_search/studies", json=payload, params=params, headers=get_headers())

    if response.status_code == 200:
        return pd.DataFrame(response.json())
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

study_search_results = None
intervention_search_results = None
condition_search_results = None
outcome_search_results = None

uploaded_file = st.file_uploader("Upload your RIS, CGI or NBIB file", type=["ris", "nbib", "cgi"])
if uploaded_file is not None:
    # Read the file content as bytes
    file_content = uploaded_file.getvalue()
    
    # Create a multipart form-data request
    files = {'file': (uploaded_file.name, file_content, 'application/octet-stream')}
    headers = {"Authorization": f"Bearer {st.session_state.get('access_token',None)}"}
    
    # Send the file to FastAPI server for processing
    response = requests.post(BACKEND_API + f"/upload", files=files, headers=get_headers())
    
    if response.status_code != 200:
        st.error(f"Error: {response.text}")
    else:
        #st.json(response.json())  # Display parsed JSON response from FastAPI

        index = st.number_input(
            "Select a report", value=0, min_value=0, max_value=len(response.json()) - 1, step=1
        )

        selected_report = response.json()[index]
    
        title = selected_report['title']
        abstract = selected_report['abstract']
        authors = selected_report['authors']
        trial_registration_id = selected_report['trial_registration_id']
        current_trial_id = trial_registration_id

        display_title = title
        display_abstract = abstract
        display_authors = authors

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

        tag_sources = st.multiselect(
            "Sources for tags",
            ["Meerkat", "MeSH"],
            default="Meerkat",
            max_selections=2,
            accept_new_options=False,
        )

        if st.button("Search", icon=":material/search:", use_container_width=True,  key="search_1") and (title != "" or abstract != ""):
            text_to_process = []
            if title:
                text_to_process.append(title)
            if abstract:
                text_to_process.append(abstract)
            text_to_process = "\n".join(text_to_process)
            current_model, current_embedding, current_aspect_embeddings = get_embeddings(text_to_process)
            if current_model is None or current_embedding is None or current_aspect_embeddings is None:
                st.error("Could not parse inputs")

            study_search_results = get_similar_studies(current_embedding, current_model, trial_id=current_trial_id)
            intervention_search_results = get_similar_tags(current_aspect_embeddings['intervention'], current_model, tag_sources, "interventions")
            condition_search_results = get_similar_tags(current_aspect_embeddings['condition'], current_model, tag_sources,"conditions")
            outcome_search_results = get_similar_tags(current_aspect_embeddings['outcome'], current_model, tag_sources,"outcomes")

if study_search_results is not None:
    tab1, tab2, tab3, tab4 = st.tabs(["Studies", "Interventions", "Conditions", "Outcomes"])

    with tab1:
        if study_search_results is not None:
            study_search_results['CRGStudyID'] = './Study?id=' + study_search_results['CRGStudyID'].astype(str) + "&token=" + st.session_state['access_token']
            st.dataframe(study_search_results, column_config={"CRGStudyID": st.column_config.LinkColumn("CRGStudyID", pinned=True, display_text=r"\.\/Study\?id=(.+)&token")})
        else:
            st.write("No search results")

    with tab2:
        if intervention_search_results is not None:
            st.dataframe(intervention_search_results)
        else:
            st.write("No search results")

    with tab3:
        if condition_search_results is not None:
            st.dataframe(condition_search_results)
        else:
            st.write("No search results")

    with tab4:
        if outcome_search_results is not None:
            st.dataframe(outcome_search_results)
        else:
            st.write("No search results")

with st.sidebar:
    show_login()