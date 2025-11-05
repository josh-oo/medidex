import streamlit as st
import requests
import os
import base64
import json
from dotenv import load_dotenv

load_dotenv()

BACKEND_API = os.getenv('BACKEND_API')

def get_headers():
    headers = {}
    if "access_token" in st.session_state:
        headers = {"Authorization": f"Bearer {st.session_state['access_token']}"}
    return headers

def decode_jwt(token: str):
    try:
        header, payload, signature = token.split('.')
        # Add padding if needed
        payload += '=' * (-len(payload) % 4)
        decoded_bytes = base64.urlsafe_b64decode(payload)
        decoded_payload = json.loads(decoded_bytes)
        return decoded_payload
    except Exception as e:
        print(f"Error decoding JWT: {e}")
        return None
    
def token_auth(token):
    payload = decode_jwt(token)
    st.session_state['access_token'] = token
    st.session_state['name'] = payload['sub']
    st.session_state['role'] = payload['role']
    st.session_state['id'] = payload['id']
    st.rerun()

def show_login():
    with st.form("login", enter_to_submit=False):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")

        response = None
        #if st.form_submit_button("Sign Up", use_container_width=True, type="secondary"):
        with st.popover("Sign Up", use_container_width=True):
            repeat_password = st.text_input("Repeat Password", type="password")
            if st.form_submit_button("Sign Up", use_container_width=True, type="secondary"):
                if password == repeat_password:
                    payload = {"email": email, "password": password}
                    response = requests.post(BACKEND_API + "/signup", json=payload)
                else:
                    st.error("Passwords do not match")
                
                if response.status_code == 200:
                    token = response.json()['access_token']
                    token_auth(token)
                else:
                    st.error(f"Error: {response.status_code} - {response.text}")

        if st.form_submit_button("Login", use_container_width=True, type="primary"):
            data = {
                "username": email,
                "password": password,
            }

            headers = {
                "Content-Type": "application/x-www-form-urlencoded"
            }
            response = requests.post(BACKEND_API + "/login", data=data, headers=headers)

            if response.status_code == 200:
                token = response.json()['access_token']
                token_auth(token)
        
        if response is not None:
            if response.status_code != 200:
                st.error(f"Error: {response.status_code} - {response.text}")

def show_logout():
    if st.button("Logout - " + st.session_state.name, use_container_width=True):
        response = requests.post(BACKEND_API + "/logout", headers=get_headers())
        if response.status_code == 201:
            st.session_state.pop('access_token')
            st.session_state.pop('name')
            st.session_state.pop('role')
            st.switch_page(st.Page(show_login, title="Login", icon=":material/login:"))