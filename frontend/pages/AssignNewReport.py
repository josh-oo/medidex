import streamlit as st
import pandas as pd
import requests
import os
from dotenv import load_dotenv

load_dotenv()

BACKEND_API = os.getenv('BACKEND_API')

current_embedding = None
current_aspect_embeddings = None
current_model = None

def get_embeddings(text):
    payload = {"text": text}
    response = requests.post(BACKEND_API + "/embedding/aspects", json=payload)

    if response.status_code == 200:
        data = response.json()
        embedding = data.pop("embedding")
        model = data.pop("model_id")
        aspect_embeddings = data

        return model, embedding, aspect_embeddings
        
    else:
        print("Request failed:", response.status_code, response.text)
        return None, None, None
    
def get_similar_studies(embedding, model):
    payload = {"embedding": embedding, "model_id": model}
    response = requests.post(BACKEND_API + "/similarity_search/studies", json=payload)

    if response.status_code == 200:
        return pd.DataFrame(response.json())
    else:
        print("Request failed:", response.status_code, response.text)
        return None

def get_similar_tags(embedding, model, tag):
    payload = {"embedding": embedding, "model_id": model}
    response = requests.post(BACKEND_API + f"/similarity_search/tags/{tag}", json=payload)

    if response.status_code == 200:
        return pd.DataFrame(response.json())
    else:
        print("Request failed:", response.status_code, response.text)
        return None

title = st.text_input("Title")
abstract = st.text_area("Abstract")

study_search_results = None
intervention_search_results = None
condition_search_results = None
outcome_search_results = None

if st.button("Search", icon=":material/search:", use_container_width=True,  key="search_1") and title + abstract != "":
    text_to_process =title + "\n" + abstract
    current_model, current_embedding, current_aspect_embeddings = get_embeddings(text_to_process)
    if current_model is None or current_embedding is None or current_aspect_embeddings is None:
        st.error("Could not parse inputs")

    study_search_results = get_similar_studies(current_embedding, current_model)
    intervention_search_results = get_similar_tags(current_aspect_embeddings['intervention'], current_model, "interventions")
    condition_search_results = get_similar_tags(current_aspect_embeddings['condition'], current_model, "conditions")
    outcome_search_results = get_similar_tags(current_aspect_embeddings['outcome'], current_model, "outcomes")

tab1, tab2, tab3, tab4 = st.tabs(["Studies", "Interventions", "Conditions", "Outcomes"])

with tab1:
    if study_search_results is not None:
        st.dataframe(study_search_results)
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