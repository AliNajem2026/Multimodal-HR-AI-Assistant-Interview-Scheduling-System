import os
import streamlit as st
import requests
from datetime import datetime

st.set_page_config(
    page_title="Multimodal HR AI Assistant",
    page_icon="📅",
    layout="centered",
)

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000/api/v1/schedule")

if "phase_step" not in st.session_state:
    st.session_state.phase_step = 1
if "candidate_data" not in st.session_state:
    st.session_state.candidate_data = None
if "proposed_slots" not in st.session_state:
    st.session_state.proposed_slots = []
if "booking_metadata" not in st.session_state:
    st.session_state.booking_metadata = None
if "week_offset" not in st.session_state:
    st.session_state.week_offset = 0

st.markdown(
    "<h1 style='color:#22d3ee;margin-bottom:0'>MULTIMODAL HR AI ASSISTANT</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='color:#94a3b8;font-size:0.85rem;font-weight:bold;letter-spacing:1px;"
    "margin-top:0;margin-bottom:30px'>POWERED BY CLAUDE AI + GOOGLE CALENDAR</p>",
    unsafe_allow_html=True,
)

# ── Phase 1: Parse candidate input ──────────────────────────────────────────
st.markdown("### Phase 1 — Parse Candidate Request")
raw_input = st.text_area(
    label="Candidate Input",
    placeholder=(
        "Paste the candidate's email or form submission here.\n\n"
        "Example:\n"
        "Hi, I'm Sarah Johnson (sarah.johnson@email.com). "
        "I'd like to apply for the Senior Backend Engineer role on your platform team."
    ),
    height=160,
    label_visibility="collapsed",
)

if st.button("Process with Claude AI", type="primary", use_container_width=True):
    if not raw_input.strip():
        st.warning("Please paste candidate text before submitting.")
    else:
        with st.spinner("Claude AI is extracting candidate info and checking calendar availability…"):
            try:
                resp = requests.post(
                    f"{API_BASE}/request",
                    json={"raw_text": raw_input, "week_offset": 0},
                    timeout=30,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    st.session_state.candidate_data = data["candidate"]
                    st.session_state.proposed_slots = data["proposed_slots"]
                    st.session_state.week_offset = data.get("week_offset", 0)
                    st.session_state.phase_step = 2
                    st.rerun()
                elif resp.status_code == 422:
                    st.error(
                        "Could not extract required fields from the text. "
                        "Make sure the input includes a name, email address, and job role."
                    )
                else:
                    try:
                        detail = resp.json().get("detail", resp.text)
                    except Exception:
                        detail = resp.text
                    st.error(f"Backend error: {detail}")
            except requests.exceptions.ConnectionError:
                st.error(
                    "Cannot reach the backend. Make sure the FastAPI server is running: "
                    "`uvicorn app.main:app --reload`"
                )
            except Exception as exc:
                st.error(f"Unexpected error: {exc}")

# ── Phase 2: Show extracted info and slot picker ─────────────────────────────
if st.session_state.phase_step >= 2 and st.session_state.candidate_data:
    st.markdown("---")
    st.markdown("### Phase 2 — Candidate Profile & Slot Selection")

    with st.expander("Extracted Candidate Profile", expanded=True):
        col1, col2 = st.columns(2)
        c = st.session_state.candidate_data
        with col1:
            st.markdown(f"**Name:** {c.get('candidate_name', '—')}")
            st.markdown(f"**Email:** {c.get('candidate_email', '—')}")
        with col2:
            st.markdown(f"**Role:** {c.get('target_role', '—')}")
            st.markdown(f"**Department:** {c.get('department', '—')}")

    # Compute week label for context
    week_offset = st.session_state.week_offset
    if week_offset == 0:
        week_label = "next week"
    elif week_offset == 1:
        week_label = "the week after next"
    else:
        week_label = f"{week_offset + 1} weeks from now"

    st.info(f"Select a time slot for **{week_label}**. If none work, decline to see the following week.")

    for slot in st.session_state.proposed_slots:
        try:
            dt = datetime.fromisoformat(slot)
            label = dt.strftime("%A, %b %d %Y  ·  %I:%M %p")
        except ValueError:
            label = slot

        if st.button(f"📅  {label}", use_container_width=True):
            with st.spinner("Creating calendar event and Google Meet link…"):
                try:
                    confirm = requests.post(
                        f"{API_BASE}/confirm",
                        json={
                            "candidate_email": c["candidate_email"],
                            "selected_slot": slot,
                        },
                        timeout=30,
                    )
                    if confirm.status_code == 201:
                        st.session_state.booking_metadata = confirm.json()["booking_metadata"]
                        st.session_state.phase_step = 3
                        st.rerun()

                    else:
                        try:
                            detail = confirm.json().get("detail", confirm.text)
                        except Exception:
                            detail = confirm.text
                        st.error(f"Booking failed: {detail}")
                except Exception as exc:
                    st.error(f"Error: {exc}")

    st.markdown("---")
    next_week_offset = st.session_state.week_offset + 1
    if st.button(
        f"None of these work — suggest the following week",
        use_container_width=True,
        type="secondary",
    ):
        with st.spinner(f"Finding slots for week {next_week_offset + 1}…"):
            try:
                resp = requests.post(
                    f"{API_BASE}/more-slots",
                    json={
                        "candidate_email": c["candidate_email"],
                        "week_offset": next_week_offset,
                    },
                    timeout=30,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    st.session_state.proposed_slots = data["proposed_slots"]
                    st.session_state.week_offset = data.get("week_offset", next_week_offset)
                    st.rerun()
                else:
                    try:
                        detail = resp.json().get("detail", resp.text)
                    except Exception:
                        detail = resp.text
                    st.error(f"Could not fetch next-week slots: {detail}")
            except Exception as exc:
                st.error(f"Error: {exc}")

# ── Phase 3: Confirmation banner ─────────────────────────────────────────────
if st.session_state.phase_step == 3 and st.session_state.booking_metadata:
    st.markdown("---")
    st.balloons()
    st.success("### Interview Scheduled Successfully!")

    meta = st.session_state.booking_metadata
    if meta.get("email_sent"):
        st.info("📧 Confirmation email sent to the candidate.")
    meet_url = meta["google_meet_url"]
    st.markdown(
        f"**Google Meet:** [{meet_url}]({meet_url})  \n"
        f"**Time:** `{meta['locked_slot_time']}`  \n"
        f"**Calendar Event ID:** `{meta['event_id']}`"
    )

    st.markdown("**Attendees:**")
    for attendee in meta["attendees"]:
        st.markdown(f"- `{attendee}`")

    if st.button("Schedule Another Interview", use_container_width=True):
        st.session_state.phase_step = 1
        st.session_state.candidate_data = None
        st.session_state.proposed_slots = []
        st.session_state.booking_metadata = None
        st.session_state.week_offset = 0
        st.rerun()
