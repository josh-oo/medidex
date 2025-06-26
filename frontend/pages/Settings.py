import streamlit as st
import pandas as pd
import requests
import os
from dotenv import load_dotenv
from utils.login import show_login, get_headers

load_dotenv()

BACKEND_API = os.getenv('BACKEND_API')

def update_user(user_id, field, value):
    payload = {}
    payload[field] = value
    response = requests.put(BACKEND_API + f"/user/{user_id}",headers=get_headers(), json=payload)

    if response.status_code == 200:
        st.rerun()
    else:
        print("Request failed:", response.status_code, response.text)
        st.error(response.text)

def get_users():
    response = requests.get(BACKEND_API + "/users",headers=get_headers())

    if response.status_code == 200:
        return pd.DataFrame(response.json())
    else:
        print("Request failed:", response.status_code, response.text)
        return None
    
def get_api_keys(owner):
    response = requests.get(BACKEND_API + f"/api_keys/{owner}", headers=get_headers())

    if response.status_code == 200:
        return response.json()
    else:
        print("Request failed:", response.status_code, response.text)
        return None
    
def create_api_key(owner):
    response = requests.post(BACKEND_API + f"/api_key/{owner}", headers=get_headers())

    if response.status_code == 200:
        return response.json()
    else:
        print("Request failed:", response.status_code, response.text)
        return None
    
def revoke_api_key(api_key_id):
    response = requests.delete(BACKEND_API + f"/api_key/{api_key_id}", headers=get_headers())

    if response.status_code == 200:
        return response.json()
    else:
        print("Request failed:", response.status_code, response.text)
        return None

@st.dialog("Your new API KEY")
def show_api_key(api_key):
    st.write("This is the only time you see your API key:")
    st.code(api_key)

if "id" in st.session_state:
    st.header("API Keys")
    all_api_keys = []
    all_api_keys = get_api_keys(st.session_state['id'])
    if all_api_keys and len(all_api_keys) > 0:
        for i, api_key in enumerate(all_api_keys):
            col1, col2 = st.columns([5, 1])
            with col1:
                st.write(api_key[0])
            with col2:
                if st.button("Revoke", key=f"delete_{i}"):
                    revoke_api_key(api_key[0])
                    st.rerun()

    if st.button("Create new API key"):
        api_key = create_api_key(st.session_state['id'])
        print("Api key: ", api_key)
        if api_key:
            st.rerun()
            show_api_key(api_key['api_key'])


if "role" in st.session_state and st.session_state['role'] == "admin":
    all_users = get_users()
    if all_users is not None:
        st.header("Users")
        st.dataframe(all_users)
        selected_user = st.selectbox(
            "Edit user: ",
            all_users['id'],
            index=None,
            accept_new_options=False,
        )
        selected_attribute = st.selectbox(
            "Attribute: ",
            ['role', 'verified', 'email'],
            index=None,
            accept_new_options=False,
        )
        value = st.text_input("Value")
        if st.button("Apply"):
            update_user(selected_user, selected_attribute, value)

#if st.button("Test"):
#    text = "A two-arm, randomised feasibility trial using link workers to improve dental visiting in people with severe mental illness: a protocol paper"
#    text += "\n" + "BACKGROUND: People with severe mental illness (e.g. psychosis, bipolar disorder) experience poor oral health compared to the general population as shown by more decayed, missing and filled teeth and a higher prevalence of periodontal disease. Attending dental services allows treatment of oral health problems and support for prevention. However, people with severe mental illness face multiple barriers to attending routine dental appointments and often struggle to access care. Link work interventions use non‐clinical support staff to afford vulnerable populations the capacity, opportunity, and motivation to navigate use of services. The authors have co‐developed with service users a link work intervention for supporting people with severe mental illness to access routine dental appointments. The Mouth Matters in Mental Health Study aims to explore the feasibility and acceptability of this intervention within the context of a feasibility randomised controlled trial (RCT) measuring outcomes related to the recruitment of participants, completion of assessments, and adherence to the intervention. The trial will closely monitor the safety of the intervention and trial procedures. METHODS: A feasibility RCT with 1:1 allocation to two arms: treatment as usual (control) or treatment as usual plus a link work intervention (treatment). The intervention consists of six sessions with a link worker over 9 months. Participants will be adults with severe mental illness receiving clinical input from secondary care mental health service and who have not attended a planned dental appointment in the past 3 years. Assessments will take place at baseline and after 9 months. The target recruitment total is 84 participants from across three NHS Trusts. A subset of participants and key stakeholders will complete qualitative interviews to explore the acceptability of the intervention and trial procedures. DISCUSSION: The link work intervention aims to improve dental access and reduce oral health inequalities in people with severe mental illness. There is a dearth of research relating to interventions that attempt to improve oral health outcomes in people with mental illness and the collected feasibility data will offer insights into this important area. TRIAL REGISTRATION: The trial was preregistered on ISRCTN (ISRCTN13650779) and ClinicalTrials.gov (NCT05545228)."
#    payload = {'text': text, "topK": 10}
#    headers = {'X-API-Key': "HS3PIWb8ics.XQFE7tSt6URMwcySgcmR9d32gWrSMwsuGK7nWU4TIiQ"}
#    response = requests.post(BACKEND_API + f"/api/v1/analyze",headers=headers, json=payload)
#
#    st.write(response)
#    if response.status_code == 200:
#        st.json(response.text)
#    else:
#        print("Request failed:", response.status_code, response.text)
#        st.error(response.text)

with st.sidebar:
    show_login()

