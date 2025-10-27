import streamlit as st
import pandas as pd
import requests
import os
from dotenv import load_dotenv
from utils.login import show_logout, get_headers

load_dotenv()

BACKEND_API = os.getenv('BACKEND_API')

def update_user(user_id, field, value):
    payload = {}
    payload[field] = value
    response = requests.put(BACKEND_API + f"/users/{user_id}",headers=get_headers(), json=payload)

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
    response = requests.get(BACKEND_API + f"/users/{owner}/api_keys", headers=get_headers())

    if response.status_code == 200:
        return response.json()
    else:
        print("Request failed:", response.status_code, response.text)
        return None
    
def create_api_key(owner):
    response = requests.put(BACKEND_API + f"/users/{owner}/api_keys", headers=get_headers())

    if response.status_code == 200:
        return response.json()
    else:
        print("Request failed:", response.status_code, response.text)
        return None
    
def revoke_api_key(owner, api_key_id):
    response = requests.delete(BACKEND_API + f"/users/api_keys/{api_key_id}", headers=get_headers())

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
                    revoke_api_key(st.session_state['id'], api_key[0])
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

with st.sidebar:
    show_logout()

