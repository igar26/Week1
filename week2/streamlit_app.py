"""Run from week2: streamlit run streamlit_app.py --server.port 8502."""
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv

st.set_page_config(page_title='After Hours · Find your shared yes',page_icon=':material/nightlife:',layout='wide',initial_sidebar_state='collapsed')
load_dotenv(Path(__file__).parent/'.env')
from referee import ui
from referee.codex import AgentError
from referee.providers import ProviderError
from referee.graph import GraphError
from referee.sms import SMSError
from referee.security import local_only,private_file

try:
    local_only(st.get_option('server.address'))
    for secret in [Path(__file__).parent/'.env',Path(__file__).parent/'.streamlit/secrets.toml']:
        if secret.exists():private_file(secret)
except ValueError as exc:
    st.error(str(exc));st.stop()

if 'page' not in st.session_state:st.session_state.page='Home'
from referee.simple import consume_invitation
consume_invitation()
ui.styles()
try:
    ui.header()
    {'Home':ui.home,'Your group':ui.group_page,'Advanced group':ui.advanced_group_page,'Discover':ui.discover_page,
     'The vote':ui.vote_page,'Our adventures':ui.memories_page,'Help':ui.help_page}[st.session_state.page]()
except (ValueError,AgentError,ProviderError,GraphError,SMSError) as exc:
    st.error(str(exc))
except Exception:
    st.error('This action could not finish. Your saved group data is still local. Check setup in Help, then retry.')
st.space('small')
