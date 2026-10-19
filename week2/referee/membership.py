"""Explicit group departure, separate from closing a browser session."""
import streamlit as st


def group_settings(store,key):
    member=store.member(key);group=store.group(key)
    others=[r for r in store.roster(key) if r['id']!=member['id']]
    with st.expander('Group settings'):
        st.subheader('Leave this group')
        successor=None
        if group['owner']==member['id'] and others:
            names={r['id']:r['name'] for r in others}
            successor=st.selectbox('Choose the next coordinator',[None]+list(names),format_func=lambda mid:names.get(mid,'Choose a member'))
            st.caption('Coordinator access transfers to that member when you leave.')
        elif not others:st.caption('You are the last member. Leaving closes the group to its current invitations.')
        st.caption('Leaving removes your access. Shared memories remain for the group unless you choose to delete your own below. An unfinished plan will need agreement again; a confirmed venue and completed memories are kept.')
        remove=st.checkbox('Delete my shared photos and captions when I leave',key='leave_delete_'+member['id'])
        confirm=st.checkbox('I understand and want to leave this group',key='leave_confirm_'+member['id'])
        needs_successor=group['owner']==member['id'] and bool(others)
        if st.button('Leave group',disabled=not confirm or (needs_successor and not successor),key='leave_group_'+member['id']):
            store.leave_group(key,successor,remove)
            for name in list(st.session_state):del st.session_state[name]
            st.session_state.update(page='Home',notice='You have left the group.')
            st.rerun()
