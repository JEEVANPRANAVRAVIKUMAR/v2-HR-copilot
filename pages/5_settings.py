"""
Settings page — configuration, feature toggles, and app info.
"""

from __future__ import annotations

import streamlit as st
import inspect

from ui_helpers import (
    load_css,
    render_sidebar,
    info_card,
)

st.set_page_config(
    page_title="⚙️ Settings",
    page_icon="⚙️",
    layout="wide",
)

load_css()
render_sidebar()

st.markdown(
    '<h2 style="color:#1A365D;margin:0 0 0.5rem;">⚙️ Settings</h2>',
    unsafe_allow_html=True,
)

# ---- App Info ----
st.markdown(
    '<div class="card">'
    "<h3>Application Info</h3>",
    unsafe_allow_html=True,
)
try:
    from config import get_settings
    settings = get_settings()
    st.markdown(f"**Name:** {settings.app_name}")
    st.markdown(f"**Version:** {settings.app_version}")
    st.markdown(f"**LLM Model:** {settings.groq_model}")
    st.markdown(f"**Embedding Model:** {settings.embedding_model}")
except Exception:
    st.markdown("**Name:** Enterprise HR AI Assistant")
    st.markdown("**Version:** 2.0.0")
st.markdown("</div>", unsafe_allow_html=True)

# ---- AI Features ----
st.markdown(
    '<div class="card">'
    "<h3>🤖 Advanced AI Features</h3>",
    unsafe_allow_html=True,
)

if "advanced_ai" not in st.session_state:
    try:
        from utils.logger import get_logger
        from services.advanced_ai_service import AdvancedAIService
        st.session_state.advanced_ai = AdvancedAIService(get_logger("settings_page"))
    except Exception:
        st.session_state.advanced_ai = None

features = [
    ("🎓 Course Recommendations", "recommend_courses"),
    ("📈 Promotion Suggestions", "suggest_promotions"),
    ("🔍 Duplicate Detection", "detect_duplicates"),
    ("📄 Resume Matching", "match_resume"),
    ("🔮 Hiring Prediction", "predict_hiring_needs"),
    ("💡 Workforce Insights", "workforce_insights"),
]

for label, method_name in features:
    with st.container():
        c1, c2 = st.columns([3, 1])
        with c1:
            st.markdown(f"**{label}**")
        with c2:
            if st.button("Check", key=f"check_{method_name}", use_container_width=True):
                if st.session_state.advanced_ai:
                    try:
                        method = getattr(st.session_state.advanced_ai, method_name)
                        sig = inspect.signature(method)
                        required = [
                            p.name for p in sig.parameters.values()
                            if p.default is inspect.Parameter.empty and p.kind in (
                                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                                inspect.Parameter.POSITIONAL_ONLY,
                            )
                        ]
                        if required:
                            result = method("demo_employee_no")
                        else:
                            result = method()
                        if result.get("status") == "coming_soon":
                            st.info(f"⏳ {result.get('description', 'Coming soon.')}")
                        else:
                            st.success("Ready!")
                    except Exception:
                        st.info("⏳ Coming soon.")
                else:
                    st.info("⏳ Coming soon.")

st.markdown("</div>", unsafe_allow_html=True)

# ---- API Configuration ----
st.markdown(
    '<div class="card">'
    "<h3>🔑 API Configuration</h3>",
    unsafe_allow_html=True,
)
try:
    key = settings.groq_api_key
    masked = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
    st.markdown(f"**Groq API Key:** `{masked}`")
except Exception:
    st.markdown("**Groq API Key:** Not configured")

st.markdown(f"**Supabase URL:** `{settings.supabase_url}`" if hasattr(settings, 'supabase_url') else "")
st.markdown("</div>", unsafe_allow_html=True)

# ---- Conversation ----
st.markdown(
    '<div class="card">'
    "<h3>💬 Conversation</h3>",
    unsafe_allow_html=True,
)

if "messages" in st.session_state and st.session_state.messages:
    msg_count = len(st.session_state.messages)
    st.markdown(f"Current session messages: **{msg_count}**")
    if st.button("Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        if "memory" in st.session_state:
            st.session_state.memory.clear()
        st.rerun()
else:
    st.markdown("No messages in the current session.")

st.markdown("</div>", unsafe_allow_html=True)

# ---- Footer ----
st.markdown(
    '<div style="text-align:center;margin-top:2rem;color:#94A3B8;font-size:0.8rem;">'
    "Enterprise HR AI Assistant v2.0</div>",
    unsafe_allow_html=True,
)
