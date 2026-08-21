import datetime as dt
import html as html_lib
import io
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    from google_drive import (
        upload_file, upload_text, upload_excel, needs_auth, run_first_time_auth,
        list_child_folders, list_files_in_folder, download_file,
        ensure_subfolder, move_file,
    )
    GDRIVE_AVAILABLE = True
except ImportError:
    GDRIVE_AVAILABLE = False

try:
    from platform_poster import post_line_oa, post_line_oa_with_image, post_facebook, post_instagram
    POSTER_AVAILABLE = True
except ImportError:
    POSTER_AVAILABLE = False

try:
    from youtube_uploader import upload_video as upload_youtube
    YOUTUBE_AVAILABLE = True
except ImportError:
    YOUTUBE_AVAILABLE = False

try:
    from chat_inbox import fetch_conversations, send_message, generate_ai_reply, DEFAULT_PROFILE
    CHAT_INBOX_AVAILABLE = True
except ImportError:
    CHAT_INBOX_AVAILABLE = False

try:
    import affiliate_ui
    AFFILIATE_AVAILABLE = True
except ImportError:
    AFFILIATE_AVAILABLE = False

try:
    import content_copilot
    COPILOT_AVAILABLE = True
except ImportError:
    COPILOT_AVAILABLE = False

try:
    import brainstorm
    BRAINSTORM_AVAILABLE = True
except ImportError:
    BRAINSTORM_AVAILABLE = False

try:
    import canva_client
    CANVA_AVAILABLE = True
except ImportError:
    CANVA_AVAILABLE = False

try:
    import scene_presets
    SCENES_AVAILABLE = True
except ImportError:
    SCENES_AVAILABLE = False

try:
    import tiktok_poster
    TIKTOK_AVAILABLE = True
except ImportError:
    TIKTOK_AVAILABLE = False

try:
    import flow_sync
    FLOW_SYNC_AVAILABLE = True
except ImportError:
    FLOW_SYNC_AVAILABLE = False

try:
    import attachments
    ATTACH_AVAILABLE = True
except ImportError:
    ATTACH_AVAILABLE = False

try:
    import queue_review
    QUEUE_REVIEW_AVAILABLE = True
except ImportError:
    QUEUE_REVIEW_AVAILABLE = False

try:
    import secrets_store
    SECRETS_STORE_AVAILABLE = True
except ImportError:
    SECRETS_STORE_AVAILABLE = False

try:
    import facebook_auth
    FB_AUTH_AVAILABLE = True
except ImportError:
    FB_AUTH_AVAILABLE = False

# Top-level mode switch labels (shop owner vs affiliate marketing)
MODE_SHOP = "🏪 ร้านของฉัน"
MODE_AFFILIATE = "🚀 แอฟฟิลิเอต"


def _upload_to_drive_public(file_bytes: bytes, name: str, mime: str) -> str | None:
    """Helper: upload bytes to Drive, return public URL."""
    try:
        from google_drive import upload_image_public
        return upload_image_public(file_bytes, name, GDRIVE_FOLDER_ID, mime_type=mime)
    except Exception as e:
        return None


PLATFORM_THAI_NAMES = {
    "line_oa": "💚 LINE OA", "facebook": "🔵 Facebook", "instagram": "🟣 Instagram",
    "tiktok": "⬛ TikTok", "youtube": "🔴 YouTube",
}


def _record_post(platform_key: str, ok: bool, detail: str) -> None:
    """Append a post attempt to session history."""
    st.session_state.setdefault("post_history", []).append({
        "เวลา": dt.datetime.now().strftime("%d/%m %H:%M"),
        "แพลตฟอร์ม": PLATFORM_THAI_NAMES.get(platform_key, platform_key),
        "สถานะ": "✅ สำเร็จ" if ok else "❌ ไม่สำเร็จ",
        "รายละเอียด": detail[:160],
    })


def _do_post(platform_key: str, content: str,
             line_token: str, fb_token: str, fb_page_id: str,
             ig_business_id: str = "",
             image_bytes: bytes | None = None, image_name: str = "image.jpg",
             video_bytes: bytes | None = None, video_name: str = "video.mp4",
             quiet: bool = False) -> tuple[bool, str]:
    """Post to one platform. Returns (ok, message) and records history."""
    ok, msg = False, ""

    if platform_key == "line_oa":
        if not line_token:
            msg = "ใส่ LINE OA Token ในแถบซ้ายก่อน"
        else:
            with st.spinner("กำลังส่งไป LINE OA..."):
                if image_bytes:
                    if not GDRIVE_AVAILABLE or needs_auth():
                        msg = "ต้อง authorize Google Drive ก่อนส่งภาพ"
                    else:
                        img_url = _upload_to_drive_public(image_bytes, image_name, "image/jpeg")
                        if not img_url:
                            msg = "Upload ภาพไม่ได้"
                        else:
                            ok, msg = post_line_oa_with_image(content, img_url, line_token)
                else:
                    ok, msg = post_line_oa(content, line_token)

    elif platform_key == "facebook":
        if not fb_token or not fb_page_id:
            msg = "ใส่ Facebook Token และ Page ID ก่อน"
        else:
            with st.spinner("กำลังโพสต์ Facebook..."):
                ok, msg = post_facebook(content, fb_token, fb_page_id,
                                        image_bytes=image_bytes, image_name=image_name)

    elif platform_key == "instagram":
        if not fb_token or not ig_business_id:
            msg = "ใส่ FB Token + IG Business ID ก่อน"
        elif not image_bytes and not video_bytes:
            msg = "IG ต้องมีรูปหรือวิดีโอ"
        elif not GDRIVE_AVAILABLE or needs_auth():
            msg = "ต้อง authorize Google Drive ก่อน"
        else:
            with st.spinner("กำลังโพสต์ Instagram (วิดีโออาจใช้เวลานาน)..."):
                img_url = vid_url = None
                if video_bytes:
                    vid_url = _upload_to_drive_public(video_bytes, video_name, "video/mp4")
                elif image_bytes:
                    img_url = _upload_to_drive_public(image_bytes, image_name, "image/jpeg")
                if not img_url and not vid_url:
                    msg = "Upload media ไม่ได้"
                else:
                    ok, msg = post_instagram(content, img_url, vid_url, ig_business_id, fb_token)

    elif platform_key == "youtube":
        if not video_bytes:
            msg = "YouTube ต้องมีวิดีโอ — อัปโหลดวิดีโอก่อน"
        elif not YOUTUBE_AVAILABLE:
            msg = "YouTube module ไม่ได้ติดตั้ง"
        else:
            title = content.split("\n")[0][:100] or "REVENUE AI Post"
            with st.spinner("กำลังอัปโหลด YouTube (อาจใช้เวลา 1-3 นาที)..."):
                ok, result = upload_youtube(video_bytes, title=title, description=content)
            msg = result
            if ok and not quiet:
                st.success("YouTube สำเร็จ ✅")
                st.markdown(f"[🔗 เปิดวิดีโอ]({result})")

    elif platform_key == "tiktok":
        tt_token = st.session_state.get("tiktok_token", "")
        if not video_bytes:
            msg = "TikTok ต้องมีวิดีโอ"
        elif not TIKTOK_AVAILABLE or not tt_token:
            # No token configured — fall back to the manual hand-off.
            ok, msg = True, "วิดีโอพร้อม — ดาวน์โหลดแล้วอัปโหลดในแอป TikTok"
            if not quiet:
                st.info("📥 TikTok: ใส่ Access Token ในแถบซ้ายเพื่อโพสต์อัตโนมัติ "
                        "หรือดาวน์โหลดวิดีโอไปอัปเองในแอป")
            st.session_state["tiktok_video_ready"] = True
        else:
            privacy = st.session_state.get("tiktok_privacy", "SELF_ONLY")
            with st.spinner("กำลังอัปโหลดไป TikTok (อาจใช้เวลาหลายนาที)..."):
                ok, msg = tiktok_poster.post_video(
                    video_bytes, content, tt_token, privacy=privacy)
    else:
        ok, msg = True, "บันทึกคอนเทนต์แล้ว"

    _record_post(platform_key, ok, msg)
    if not quiet and platform_key != "youtube":
        st.toast(("✅ " if ok else "❌ ") + msg, icon="✅" if ok else "❌")
    return ok, msg

def _get_gdrive_folder_id() -> str:
    """Read folder ID from Streamlit secrets, fall back to default."""
    try:
        import streamlit as st
        return st.secrets.get("google_drive", {}).get("folder_id", "") or "1-Kc-3l6C781lav4emTLCbZ202JVjExux"
    except Exception:
        return "1-Kc-3l6C781lav4emTLCbZ202JVjExux"


GDRIVE_FOLDER_ID = _get_gdrive_folder_id()


def _get_queue_root_id() -> str:
    """Root Drive folder that holds the per-platform queue subfolders
    (Facebook Post / Facebook VDO / Instragram Post / ... / TikTok VDO)."""
    try:
        import streamlit as st
        return st.secrets.get("google_drive", {}).get("queue_root_id", "") or "12sVv5PEq9KNk7JlPq0sKVUAfqvIf8Nzb"
    except Exception:
        return "12sVv5PEq9KNk7JlPq0sKVUAfqvIf8Nzb"


QUEUE_ROOT_FOLDER_ID = _get_queue_root_id()


def _get_shortcut(key: str, fallback: str) -> str:
    """Quick-link URL from secrets, falling back to the team's own workspace."""
    try:
        import streamlit as st
        return st.secrets.get("shortcuts", {}).get(key, "") or fallback
    except Exception:
        return fallback


# Where the team actually works — surfaced as one-click links so nobody has to
# hunt for the tab. Override per deployment via [shortcuts] in secrets.toml.
FLOW_PROJECT_URL = _get_shortcut(
    "flow_project",
    "https://labs.google/fx/th/tools/flow/project/c9bfbfd9-88ea-4c56-b6b5-7711df26d9b8",
)
DRIVE_FOLDER_URL = _get_shortcut(
    "drive_folder",
    f"https://drive.google.com/drive/folders/{QUEUE_ROOT_FOLDER_ID}",
)

try:
    from loyverse_connector import LoyverseConnector
    LOYVERSE_AVAILABLE = True
except ImportError:
    LOYVERSE_AVAILABLE = False

try:
    from content_studio import (
        PLATFORMS, CAMPAIGN_TYPES, TONES,
        get_content_package, build_posting_schedule, route_content,
    )
    CONTENT_STUDIO_AVAILABLE = True
except ImportError:
    CONTENT_STUDIO_AVAILABLE = False

from rfm_engine import (
    SEGMENT_META,
    compute_rfm,
    label_transactions,
    rfm_summary,
)

# ── Chart templates ────────────────────────────────────────────────────────────
_COLORWAY = ["#F59E0B", "#3B82F6", "#10B981", "#8B5CF6", "#EF4444", "#EC4899", "#06B6D4"]

pio.templates["premium_dark"] = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor="#0F172A",
        plot_bgcolor="#111827",
        font=dict(family="Inter, sans-serif", color="#9CA3AF", size=12),
        colorway=_COLORWAY,
        xaxis=dict(
            gridcolor="rgba(255,255,255,0.04)", linecolor="rgba(255,255,255,0.08)",
            tickfont=dict(color="#6B7280", size=11), zerolinecolor="rgba(255,255,255,0.06)",
        ),
        yaxis=dict(
            gridcolor="rgba(255,255,255,0.04)", linecolor="rgba(255,255,255,0.08)",
            tickfont=dict(color="#6B7280", size=11), zerolinecolor="rgba(255,255,255,0.06)",
        ),
        legend=dict(
            bgcolor="rgba(17,24,39,0.85)", bordercolor="rgba(255,255,255,0.08)",
            borderwidth=1, font=dict(color="#9CA3AF", size=11),
        ),
        title=dict(font=dict(family="Plus Jakarta Sans, sans-serif", color="#E5E7EB", size=14), x=0),
        margin=dict(l=0, r=0, t=44, b=0),
        hoverlabel=dict(
            bgcolor="#1F2937", bordercolor="rgba(255,255,255,0.1)",
            font=dict(family="Inter, sans-serif", size=12, color="#F9FAFB"),
        ),
    )
)

pio.templates["premium_light"] = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#F8F7F4",
        font=dict(family="Inter, sans-serif", color="#6B7280", size=12),
        colorway=_COLORWAY,
        xaxis=dict(
            gridcolor="rgba(0,0,0,0.06)", linecolor="rgba(0,0,0,0.08)",
            tickfont=dict(color="#9CA3AF", size=11), zerolinecolor="rgba(0,0,0,0.06)",
        ),
        yaxis=dict(
            gridcolor="rgba(0,0,0,0.06)", linecolor="rgba(0,0,0,0.08)",
            tickfont=dict(color="#9CA3AF", size=11), zerolinecolor="rgba(0,0,0,0.06)",
        ),
        legend=dict(
            bgcolor="rgba(255,255,255,0.95)", bordercolor="rgba(0,0,0,0.08)",
            borderwidth=1, font=dict(color="#6B7280", size=11),
        ),
        title=dict(font=dict(family="Plus Jakarta Sans, sans-serif", color="#111827", size=14), x=0),
        margin=dict(l=0, r=0, t=44, b=0),
        hoverlabel=dict(
            bgcolor="#FFFFFF", bordercolor="rgba(0,0,0,0.1)",
            font=dict(family="Inter, sans-serif", size=12, color="#111827"),
        ),
    )
)

pio.templates.default = "premium_dark"


def apply_premium_theme(theme: str = "dark") -> None:
    is_dark = theme == "dark"

    # ── Shared token values per theme ──────────────────────────────────────
    if is_dark:
        # Deep navy, not neutral grey. Every step is a named surface level, and
        # every text token is checked against the surface it actually sits on —
        # the previous scale bottomed out at #374151, which is 2.0:1 on this
        # background. Dark grey type on dark navy is the one thing this palette
        # must never produce, so the muted end stops at #8492A6 (5.3:1).
        bg          = "#0B1220"   # page
        bg2         = "#17243A"   # raised surface (hover, popover, nav rest)
        bg3         = "#111C2E"   # surface / card
        sidebar_bg  = "#0B1220"
        border      = "#1B2740"
        border2     = "#24324A"
        border3     = "#2E3E58"
        txt1        = "#F8FAFC"   # primary        15.9:1
        txt2        = "#E2E8F0"   # strong body    12.6:1
        txt3        = "#B6C2D2"   # secondary       8.5:1
        txt4        = "#8492A6"   # muted           5.3:1
        txt5        = "#8492A6"   # section labels  5.3:1
        txt6        = "#8492A6"   # helper text     5.3:1
        h1_color    = "#F8FAFC"
        card_bg     = "#111C2E"
        card_hover  = "0 0 0 1px rgba(245,158,11,0.28)"
        tab_hover   = "#E2E8F0"
        input_bg    = "#111C2E"
        exp_bg      = "#111C2E"
        alert_mult  = "0.10"
        alert_p_ok  = "#A7F3D0"; alert_p_info = "#BFDBFE"
        alert_p_war = "#FDE68A"; alert_p_err  = "#FECACA"
        scroll_thumb= "#24324A"; scroll_thumbh="#33456380"
        lbl_color   = "#B6C2D2"
        hr_color    = "#24324A"
        hover_label = "#17243A"
        chart_bg    = "rgba(17,28,46,0.5)"
    else:
        bg          = "#F8F7F4"
        bg2         = "#FFFFFF"
        bg3         = "#F2F4F7"
        sidebar_bg  = "#FFFFFF"
        border      = "#E8E6E1"
        border2     = "#E2E0DB"
        border3     = "#D5D3CD"
        txt1        = "#111827"
        txt2        = "#1F2937"
        txt3        = "#374151"
        txt4        = "#5B6472"  # was #6B7280 — 4.3:1 on #F8F7F4, just under AA
        txt5        = "#5B6472"  # was #9CA3AF — 2.3:1, unreadable as a label
        txt6        = "#5B6472"  # was #D1D5DB — 1.4:1, effectively invisible
        h1_color    = "#0F172A"
        card_bg     = "#FFFFFF"
        card_hover  = "0 8px 28px rgba(15,23,42,0.08),0 0 0 1px rgba(245,158,11,0.22)"
        tab_hover   = "#374151"
        input_bg    = "#FFFFFF"
        exp_bg      = "#FFFFFF"
        alert_mult  = "0.08"
        alert_p_ok  = "#065F46"; alert_p_info = "#1E40AF"
        alert_p_war = "#92400E"; alert_p_err  = "#991B1B"
        scroll_thumb= "rgba(0,0,0,0.12)";  scroll_thumbh="rgba(0,0,0,0.2)"
        lbl_color   = "#5B6472"
        hr_color    = "#E8E6E1"
        hover_label = "#FFFFFF"
        chart_bg    = "rgba(248,247,244,0.6)"

    # Brand orange is a fill colour, not a text colour. #F59E0B reads at 2.0:1 on
    # the light page — measured on the sidebar's "1/5 ช่องทาง", the selected tab
    # and the AI-mode chip, all of which failed. Fills, borders and the active
    # nav stay #F59E0B; anything that is *type* uses the darker amber from the
    # same ramp. amber-700 (#B45309) clears the plain page but lands at 4.31 on
    # the chip's own 12% amber tint, so this steps to amber-800: 8.5:1 on the
    # page, 7.4:1 inside a chip. On the dark page #F59E0B is already 8.6:1.
    accent_txt = "#F59E0B" if is_dark else "#92400E"

    # Shadows read as depth only against a light page. On a dark surface they add
    # nothing but a smudge, so dark mode separates surfaces with a border instead.
    card_shadow = (
        "0 1px 2px rgba(15,23,42,0.04),0 4px 12px rgba(15,23,42,0.05)"
        if not is_dark else "none"
    )

    st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Plus+Jakarta+Sans:wght@500;600;700;800&display=swap');

/* ── Keyframes ─────────────────────────────────────────────────────────── */
@keyframes fadeUp {{
  from {{ opacity:0; transform:translateY(10px); }}
  to   {{ opacity:1; transform:translateY(0); }}
}}
@keyframes gradientFlow {{
  0%   {{ background-position: 0% 50%; }}
  50%  {{ background-position: 100% 50%; }}
  100% {{ background-position: 0% 50%; }}
}}
@keyframes shimmer {{
  0%   {{ background-position: -200% center; }}
  100% {{ background-position: 200% center; }}
}}
@keyframes pulseGlow {{
  0%,100% {{ box-shadow: 0 0 0 0 rgba(245,158,11,0.25); }}
  50%      {{ box-shadow: 0 0 0 6px rgba(245,158,11,0); }}
}}

/* ── Base ──────────────────────────────────────────────────────────────── */
html, body, .stApp {{ font-family:'Inter',-apple-system,sans-serif !important; }}
/* Both selectors: current Streamlit marks this container with a data-testid and
   the .stApp class no longer reaches it, which left the whole page frame dark
   behind a light body — the dark border showing around the content. */
/* Prefixed with html body to outrank Streamlit's own emotion classes, which
   carry the palette from config.toml and were winning on specificity — the rule
   was present and correct but never applied. */
html body .stApp, html body [data-testid="stApp"],
html body [data-testid="stAppViewContainer"] {{
  background:{bg} !important; transition:background 0.35s ease;
}}
html body [data-testid="stSidebar"] {{ background:{sidebar_bg} !important; }}
[data-testid="stAppViewContainer"] > .main {{ background:{bg} !important; }}

/* Streamlit paints its own chrome from config.toml, which is pinned to the dark
   palette. Without these the header and the bar holding the chat box stayed
   black in light mode — a dark band across the top and bottom of a light page.
   The text colour has to follow too: config also pins that, so switching to the
   light theme left near-white type sitting on the new near-white background. */
html, body {{ background:{bg} !important; color:{txt1} !important; }}
[data-testid="stAppHeader"], header[data-testid="stHeader"] {{
  background:{bg} !important; color:{txt2} !important;
  border-bottom:1px solid {border} !important;
}}
[data-testid="stAppHeader"] *, [data-testid="stAppHeader"] svg {{
  color:{txt2} !important; fill:{txt2} !important;
}}
/* The "Stop" chip Streamlit shows while a script runs keeps its own light pill
   background, so the inherited light text on it measured 1.06:1 in dark mode. */
[data-testid="stStatusWidget"] {{ background:{bg3} !important; border-radius:999px !important; }}
[data-testid="stStatusWidget"] *, [data-testid="stStatusWidget"] svg {{
  color:{txt2} !important; fill:{txt2} !important;
}}
[data-testid="stBottom"], [data-testid="stBottomBlockContainer"] {{
  background:{bg} !important; color:{txt1} !important;
}}
[data-testid="stBottom"] * {{ color:{txt1} !important; }}
[data-testid="stChatInput"] {{
  background:{input_bg} !important; border:1px solid {border3} !important;
  border-radius:12px !important;
}}
[data-testid="stChatInput"] textarea {{
  background:transparent !important; color:{txt1} !important; font-size:1rem !important;
}}
[data-testid="stChatInput"] textarea::placeholder {{ color:{txt4} !important; }}
[data-testid="stChatMessage"] {{ background:{card_bg} !important; border:1px solid {border2} !important; }}

/* Readability: body copy was rendering at 13.4px, which is hard work at arm's
   length — measured, not assumed. The html body prefix is needed here for the
   same reason as the background rules above. */
html body [data-testid="stMarkdownContainer"] p,
html body [data-testid="stMarkdownContainer"] li {{
  font-size:1rem !important; line-height:1.65 !important;
}}
html body [data-testid="stCaptionContainer"],
html body [data-testid="stCaptionContainer"] p {{ font-size:0.9rem !important; }}
html body [data-testid="stChatInput"] textarea {{ font-size:1rem !important; }}
html body button p, html body [data-testid="stBaseButton-secondary"] p,
html body [data-testid="stBaseButton-primary"] p {{ font-size:0.95rem !important; }}
/* Measure. `layout="wide"` lets a paragraph run the full width of a 27" monitor,
   which is roughly 200 characters a line — about three times the comfortable
   reading limit. Cap it and centre it; the dashboard's charts still get room. */
.block-container {{
  padding-top:2rem !important; padding-bottom:3rem !important;
  max-width:1180px !important; margin:0 auto !important;
}}
.main .block-container > div > div > div {{ animation: fadeUp 0.4s ease both; }}

/* ── Sidebar ───────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {{
  background:{sidebar_bg} !important;
  border-right:1px solid {border} !important;
  transition:background 0.35s ease;
}}
[data-testid="stSidebar"] hr {{ border-color:{border2} !important; margin:0.75rem 0 !important; }}
[data-testid="stSidebar"] .stMarkdown strong {{
  font-size:0.68rem !important; font-weight:600 !important;
  text-transform:uppercase !important; letter-spacing:0.12em !important; color:{txt5} !important;
}}
[data-testid="stSidebar"] [data-testid="stTextInput"] input {{
  background:{input_bg} !important; border-color:{border3} !important;
  color:{txt1} !important; border-radius:8px !important; font-size:0.8rem !important;
}}
[data-testid="stSidebar"] .stCaption p {{ color:{txt6} !important; font-size:0.72rem !important; }}

/* ── Theme toggle buttons ──────────────────────────────────────────────── */
button[kind="secondary"] {{
  background:{bg3} !important; border:1px solid {border2} !important;
  color:{txt3} !important; border-radius:8px !important; font-size:0.78rem !important;
  font-weight:500 !important; transition:all 0.18s ease !important;
}}
button[kind="secondary"]:hover {{
  border-color:rgba(245,158,11,0.5) !important; color:{accent_txt} !important;
  background:{bg2} !important;
}}

/* ── Typography ────────────────────────────────────────────────────────── */
/* A page title is a label, not a light show. The animated gradient fill it used
   to carry made the most important string on every page the least legible one
   (transparent text over a moving background) — solid weight reads faster and
   is what Linear/Stripe do. */
h1 {{
  font-family:'Plus Jakarta Sans',sans-serif !important; font-weight:700 !important;
  letter-spacing:-0.025em !important; line-height:1.2 !important;
  font-size:1.75rem !important;
  color:{h1_color} !important;
  -webkit-text-fill-color:{h1_color} !important;
}}
h2 {{
  font-family:'Plus Jakarta Sans',sans-serif !important; font-weight:650 !important;
  color:{txt1} !important; letter-spacing:-0.018em !important; font-size:1.25rem !important;
}}
h3 {{
  font-family:'Plus Jakarta Sans',sans-serif !important; font-weight:600 !important;
  color:{txt2} !important; font-size:1.05rem !important;
}}
/* h4-h6 had no rule at all, so they fell through to config.toml's textColor
   (#111827) and rendered as near-black on the navy page — measured 1.04:1 on the
   "ขั้นตอน" subheadings inside the connection guides. */
h4, h5, h6 {{
  font-family:'Plus Jakarta Sans',sans-serif !important; font-weight:600 !important;
  color:{txt2} !important;
}}
/* Links inherit Streamlit's light-theme blue (#0054A3), which is 2.3:1 on navy. */
html body a, html body [data-testid="stMarkdownContainer"] a {{
  color:{"#7DB8F0" if is_dark else "#0B57A4"} !important;
  text-decoration-color:{"rgba(125,184,240,0.4)" if is_dark else "rgba(11,87,164,0.35)"} !important;
}}
/* …except link buttons, which are buttons and must match the secondary look.
   Left alone they kept a near-white fill in dark mode with pale text on top. */
html body [data-testid="stBaseLinkButton-secondary"] {{
  background:{bg3} !important; border:1px solid {border2} !important;
  border-radius:10px !important; color:{txt2} !important; text-decoration:none !important;
}}
html body [data-testid="stBaseLinkButton-secondary"] p,
html body [data-testid="stBaseLinkButton-secondary"] div {{ color:{txt2} !important; }}
html body [data-testid="stBaseLinkButton-secondary"]:hover {{
  border-color:rgba(245,158,11,0.5) !important; background:{bg2} !important;
}}
html body [data-testid="stBaseLinkButton-secondary"]:hover p {{ color:{accent_txt} !important; }}
p, .stMarkdown p {{ color:{txt3} !important; font-size:0.9375rem !important; line-height:1.65 !important; }}
.stCaption p, [data-testid="stCaptionContainer"] p {{
  color:{txt4} !important; font-size:0.8125rem !important;
}}

/* ── Metric Cards ──────────────────────────────────────────────────────── */
[data-testid="metric-container"], [data-testid="stMetric"] {{
  background:{card_bg} !important;
  border:1px solid {border} !important;
  border-top:2px solid #F59E0B !important;
  border-radius:12px !important;
  padding:1.25rem 1.5rem !important;
  box-shadow:{card_shadow} !important;
  transition:transform 0.22s cubic-bezier(.34,1.56,.64,1), box-shadow 0.22s ease !important;
  position:relative !important; overflow:hidden !important;
}}
[data-testid="metric-container"]::after, [data-testid="stMetric"]::after {{
  content:"" !important; position:absolute !important;
  top:0; left:-100%; width:60%; height:100% !important;
  background:linear-gradient(90deg,transparent,rgba(245,158,11,0.04),transparent) !important;
  transition:left 0.5s ease !important;
}}
[data-testid="metric-container"]:hover::after, [data-testid="stMetric"]:hover::after {{
  left:150% !important;
}}
[data-testid="metric-container"]:hover, [data-testid="stMetric"]:hover {{
  transform:translateY(-3px) !important;
  box-shadow:{card_hover} !important;
}}
[data-testid="stMetricValue"] > div, [data-testid="stMetricValue"] {{
  font-family:'Plus Jakarta Sans',sans-serif !important;
  font-size:1.875rem !important; font-weight:700 !important;
  color:{txt1} !important; letter-spacing:-0.04em !important;
}}
[data-testid="stMetricLabel"] > div, [data-testid="stMetricLabel"] {{
  font-size:0.68rem !important; font-weight:600 !important;
  text-transform:uppercase !important; letter-spacing:0.12em !important; color:{txt4} !important;
}}

/* ── Tabs ──────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {{
  background:transparent !important;
  border-bottom:1px solid {border2} !important; gap:0 !important;
}}
.stTabs [data-baseweb="tab"] {{
  background:transparent !important; color:{txt4} !important;
  font-size:0.875rem !important; font-weight:500 !important;
  padding:0.75rem 1.25rem !important;
  border-bottom:2px solid transparent !important; border-radius:0 !important;
  transition:color 0.15s ease !important;
}}
.stTabs [data-baseweb="tab"]:hover {{ color:{tab_hover} !important; }}
.stTabs [aria-selected="true"] {{ color:{accent_txt} !important; border-bottom-color:#F59E0B !important; font-weight:600 !important; }}
.stTabs [data-baseweb="tab-highlight"] {{ background:#F59E0B !important; height:2px !important; }}
.stTabs [data-baseweb="tab-border"] {{ background:{border2} !important; }}

/* ── Alert / Insight Cards ─────────────────────────────────────────────── */
[data-testid="stAlert"] {{
  border-radius:12px !important; border:1px solid {border} !important;
  padding:0.9rem 1rem 0.9rem 1.25rem !important; font-size:0.875rem !important;
  animation:fadeUp 0.35s ease both !important;
}}
div.stSuccess {{
  background:rgba(16,185,129,{alert_mult}) !important; border-left:3px solid #10B981 !important;
}}
div.stInfo {{
  background:rgba(59,130,246,{alert_mult}) !important; border-left:3px solid #3B82F6 !important;
}}
div.stWarning {{
  background:rgba(245,158,11,{alert_mult}) !important; border-left:3px solid #F59E0B !important;
}}
div.stError {{
  background:rgba(239,68,68,{alert_mult}) !important; border-left:3px solid #EF4444 !important;
}}
div.stSuccess p,div.stSuccess [data-testid="stMarkdownContainer"] p{{ color:{alert_p_ok} !important; }}
div.stInfo p,   div.stInfo [data-testid="stMarkdownContainer"] p   {{ color:{alert_p_info} !important; }}
div.stWarning p,div.stWarning [data-testid="stMarkdownContainer"] p{{ color:{alert_p_war} !important; }}
div.stError p,  div.stError [data-testid="stMarkdownContainer"] p  {{ color:{alert_p_err} !important; }}

/* ── Buttons ───────────────────────────────────────────────────────────── */
/* Primary buttons are amber-filled, so their label has to be dark — measured at
   1.19:1 before this rule, because the generic `p {{ color:txt3 }}` above also
   claims the <p> Streamlit puts inside every button. #0B1220 on #F59E0B is 9.4:1. */
html body [data-testid="stBaseButton-primary"],
html body [data-testid="stBaseButton-primary"] p,
html body [data-testid="stBaseButton-primaryFormSubmit"],
html body [data-testid="stBaseButton-primaryFormSubmit"] p,
html body button[kind="primary"], html body button[kind="primary"] p,
html body button[kind="primaryFormSubmit"], html body button[kind="primaryFormSubmit"] p {{
  color:#0B1220 !important; font-weight:600 !important;
}}
html body [data-testid="stBaseButton-primary"],
html body [data-testid="stBaseButton-primaryFormSubmit"],
html body button[kind="primary"], html body button[kind="primaryFormSubmit"] {{
  background:#F59E0B !important; border:1px solid #F59E0B !important;
  border-radius:10px !important; box-shadow:none !important;
}}
html body [data-testid="stBaseButton-primary"]:hover,
html body [data-testid="stBaseButton-primaryFormSubmit"]:hover,
html body button[kind="primary"]:hover, html body button[kind="primaryFormSubmit"]:hover {{
  background:#D97706 !important; border-color:#D97706 !important;
}}
/* Secondary form-submit buttons inherit the plain secondary look */
html body [data-testid="stBaseButton-secondaryFormSubmit"] {{
  background:{bg3} !important; border:1px solid {border2} !important;
  color:{txt2} !important; border-radius:10px !important;
}}
[data-testid="stDownloadButton"] button {{
  background:linear-gradient(135deg,#B45309,#F59E0B) !important;
  color:#000 !important; font-weight:700 !important; font-size:0.8125rem !important;
  border:none !important; border-radius:10px !important; letter-spacing:0.02em !important;
  box-shadow:0 4px 15px rgba(245,158,11,0.3),inset 0 1px 0 rgba(255,255,255,0.18) !important;
  transition:all 0.2s cubic-bezier(.34,1.56,.64,1) !important;
  animation:pulseGlow 2.5s ease-in-out infinite !important;
}}
[data-testid="stDownloadButton"] button:hover {{
  transform:translateY(-2px) scale(1.01) !important;
  box-shadow:0 10px 30px rgba(245,158,11,0.45) !important;
}}

/* ── Inputs ────────────────────────────────────────────────────────────── */
[data-testid="stMultiSelect"] > div > div {{
  background:{input_bg} !important; border-color:{border3} !important; color:{txt1} !important;
  border-radius:10px !important;
}}
[data-testid="stMultiSelect"] span[data-baseweb="tag"] {{
  background:rgba(245,158,11,0.12) !important; color:{accent_txt} !important;
  border:1px solid rgba(245,158,11,0.25) !important; border-radius:6px !important; font-weight:500 !important;
}}
[data-testid="stNumberInput"] input, [data-testid="stTextInput"] input {{
  background:{input_bg} !important; border-color:{border3} !important;
  color:{txt1} !important; border-radius:10px !important;
  transition:border-color 0.15s ease,box-shadow 0.15s ease !important;
}}
[data-testid="stNumberInput"] input:focus, [data-testid="stTextInput"] input:focus {{
  border-color:rgba(245,158,11,0.5) !important;
  box-shadow:0 0 0 3px rgba(245,158,11,0.1) !important;
}}

/* ── Charts ────────────────────────────────────────────────────────────── */
.stPlotlyChart {{
  border-radius:12px !important; overflow:hidden !important;
  border:1px solid {border} !important;
  box-shadow:{card_shadow} !important;
  transition:box-shadow 0.22s ease !important;
}}
.stPlotlyChart:hover {{
  box-shadow:{"0 12px 40px rgba(0,0,0,0.4)" if is_dark else "0 8px 32px rgba(0,0,0,0.1)"} !important;
}}

/* ── Table ─────────────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {{
  border:1px solid {border} !important; border-radius:12px !important;
  overflow:hidden !important; box-shadow:{card_shadow} !important;
}}

/* ── Expander ──────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {{
  background:{exp_bg} !important; border:1px solid {border2} !important;
  border-radius:12px !important; overflow:hidden !important;
  box-shadow:{card_shadow} !important;
  transition:box-shadow 0.2s ease !important;
}}
[data-testid="stExpander"]:hover {{ box-shadow:{card_hover} !important; }}
[data-testid="stExpander"] summary {{ color:{txt2} !important; font-weight:500 !important; }}
[data-testid="stExpander"] summary:hover {{ color:{txt1} !important; }}

/* ── File uploader ─────────────────────────────────────────────────────── */
[data-testid="stFileUploader"] > div {{
  background:{bg2} !important; border:1.5px dashed {border3} !important;
  border-radius:12px !important; transition:all 0.2s ease !important;
}}
[data-testid="stFileUploader"] > div:hover {{
  border-color:rgba(245,158,11,0.45) !important;
  box-shadow:0 0 0 3px rgba(245,158,11,0.06) !important;
}}

/* ── Divider ───────────────────────────────────────────────────────────── */
hr {{ border:none !important; border-top:1px solid {hr_color} !important; margin:2rem 0 !important; }}

/* ── Scrollbar ─────────────────────────────────────────────────────────── */
::-webkit-scrollbar {{ width:5px; height:5px; }}
::-webkit-scrollbar-track {{ background:transparent; }}
::-webkit-scrollbar-thumb {{ background:{scroll_thumb}; border-radius:3px; }}
::-webkit-scrollbar-thumb:hover {{ background:{scroll_thumbh}; }}

/* ── Form labels ───────────────────────────────────────────────────────── */
.stSelectbox label, .stMultiSelect label, .stDateInput label,
.stSlider label, .stNumberInput label, .stCheckbox label p {{
  color:{lbl_color} !important; font-size:0.8125rem !important; font-weight:500 !important;
}}

/* ── Date input ────────────────────────────────────────────────────────── */
[data-testid="stDateInput"] input {{
  background:{input_bg} !important; border-color:{border3} !important; color:{txt1} !important;
  border-radius:10px !important;
}}

/* ── Slider ────────────────────────────────────────────────────────────── */
[data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] {{
  background:#F59E0B !important; border-color:#F59E0B !important;
}}

/* ── Radio (main area, default look) ───────────────────────────────────── */
[data-testid="stRadio"] label p {{ color:{txt3} !important; font-size:0.875rem !important; }}
[data-testid="stRadio"] [data-baseweb="radio"] div:first-child {{
  border-color:{border3} !important;
}}

/* ── Sidebar nav: radios rendered as big, full-width tappable buttons ───── */
section[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] {{
  gap:7px !important;
}}
section[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] > label {{
  width:100% !important;
  margin:0 !important;
  padding:11px 14px !important;
  min-height:44px !important;
  border:1px solid {border2} !important;
  border-radius:11px !important;
  background:{bg2} !important;
  cursor:pointer !important;
  transition:background .15s ease, border-color .15s ease, transform .12s ease, box-shadow .15s ease !important;
  display:flex !important;
  align-items:center !important;
}}
section[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] > label:hover {{
  border-color:rgba(245,158,11,0.55) !important;
  background:{bg3} !important;
  transform:translateX(2px) !important;
}}
/* hide the tiny radio circle — the whole row is the click target, and the amber
   fill already says which one is active. Two selectors: Streamlit moved this
   control from BaseWeb to React Aria, so the old data-baseweb hook silently
   stopped matching and the dots came back. */
section[data-testid="stSidebar"] [data-testid="stRadio"] [data-baseweb="radio"] > div:first-child,
section[data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div > div:first-child {{
  display:none !important;
}}
section[data-testid="stSidebar"] [data-testid="stRadio"] label p {{
  font-size:1.02rem !important;
  font-weight:600 !important;
  letter-spacing:-0.01em !important;
  line-height:1.3 !important;
  color:{txt2} !important;
  margin:0 !important;
}}
/* make the leading emoji icon read a touch larger than the text */
section[data-testid="stSidebar"] [data-testid="stRadio"] label p::first-letter {{
  font-size:1.2em !important;
}}
/* selected option — amber highlight */
section[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] > label:has(input:checked) {{
  background:linear-gradient(135deg,rgba(245,158,11,0.20),rgba(245,158,11,0.08)) !important;
  border-color:#F59E0B !important;
  box-shadow:0 2px 12px rgba(245,158,11,0.18) !important;
}}
section[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] > label:has(input:checked) p {{
  color:{txt1} !important;
  font-weight:700 !important;
}}

/* ── Mode switch → 2-button segmented control (side by side) ────────────── */
section[data-testid="stSidebar"] .st-key-app_mode [data-testid="stRadio"] [role="radiogroup"] {{
  flex-direction:row !important;
  gap:8px !important;
}}
section[data-testid="stSidebar"] .st-key-app_mode [data-testid="stRadio"] [role="radiogroup"] > label {{
  flex:1 1 0 !important;
  width:auto !important;
  justify-content:center !important;
  text-align:center !important;
  padding:12px 6px !important;
}}
section[data-testid="stSidebar"] .st-key-app_mode [data-testid="stRadio"] [role="radiogroup"] > label:hover {{
  transform:translateY(-1px) !important;
}}
section[data-testid="stSidebar"] .st-key-app_mode [data-testid="stRadio"] label p {{
  font-size:0.84rem !important;
  white-space:nowrap !important;
}}
/* keep the mode-switch icon modest so the label fits on one line */
section[data-testid="stSidebar"] .st-key-app_mode [data-testid="stRadio"] label p::first-letter {{
  font-size:1.05em !important;
}}

/* ── Themed tables (affiliate pages) — light/dark safe, unlike st.dataframe ─ */
.fnb-table-wrap {{
  overflow-x:auto;
  border:1px solid {border2} !important;
  border-radius:12px;
  margin:0.25rem 0 0.75rem;
}}
.fnb-table {{
  width:100%;
  border-collapse:collapse;
  font-size:0.9rem;
  background:{bg2} !important;
}}
.fnb-table thead th {{
  background:{bg3} !important;
  color:{txt3} !important;
  text-align:left;
  font-weight:600;
  padding:10px 14px;
  border-bottom:1px solid {border2} !important;
  white-space:nowrap;
}}
.fnb-table tbody td {{
  color:{txt2} !important;
  padding:9px 14px;
  border-bottom:1px solid {border} !important;
  white-space:nowrap;
}}
.fnb-table tbody tr:last-child td {{ border-bottom:none !important; }}
.fnb-table tbody tr:hover td {{ background:{bg3} !important; }}

/* ── Spinner ───────────────────────────────────────────────────────────── */
[data-testid="stSpinner"] > div {{ border-top-color:#F59E0B !important; }}

/* ── Selectbox / Dropdown ──────────────────────────────────────────────── */
[data-baseweb="select"] > div {{
  background:{input_bg} !important;
  border-color:{border3} !important;
  color:{txt1} !important;
  border-radius:10px !important;
}}
[data-baseweb="select"] span {{ color:{txt1} !important; }}
[data-baseweb="popover"] > div,
[data-baseweb="popover"] ul {{
  background:{bg2} !important;
  border:1px solid {border2} !important;
  border-radius:12px !important;
  box-shadow:0 8px 32px rgba(0,0,0,{"0.4" if is_dark else "0.12"}) !important;
}}
/* dropdown options — newer Streamlit renders them as <li role="option"> whose
   text color comes from the hardcoded dark native theme (config.toml textColor
   = near-white), making them invisible on the light popover. Force the active
   theme's text color, covering nested text nodes too. */
[data-baseweb="option"],
[data-baseweb="popover"] li[role="option"],
[role="listbox"] li[role="option"] {{
  background:{bg2} !important;
  color:{txt2} !important;
}}
[data-baseweb="popover"] li[role="option"] *,
[role="listbox"] li[role="option"] * {{
  color:{txt2} !important;
}}
[data-baseweb="option"]:hover,
[data-baseweb="popover"] li[role="option"]:hover,
[data-baseweb="popover"] li[role="option"][aria-selected="true"],
[role="listbox"] li[role="option"]:hover {{
  background:{bg3} !important;
  color:{txt1} !important;
}}
[data-baseweb="popover"] li[role="option"]:hover *,
[data-baseweb="popover"] li[role="option"][aria-selected="true"] * {{
  color:{txt1} !important;
}}

/* ── Text Area ─────────────────────────────────────────────────────────── */
[data-testid="stTextArea"] textarea {{
  background:{input_bg} !important;
  border-color:{border3} !important;
  color:{txt1} !important;
  border-radius:10px !important;
}}
[data-testid="stTextArea"] textarea:focus {{
  border-color:rgba(245,158,11,0.5) !important;
  box-shadow:0 0 0 3px rgba(245,158,11,0.1) !important;
}}

/* ── File uploader inner ───────────────────────────────────────────────── */
[data-testid="stFileUploaderDropzone"],
[data-testid="stFileUploaderDropzoneInput"] + div {{
  background:{bg2} !important;
  color:{txt3} !important;
}}
[data-testid="stFileUploaderDropzone"] button {{
  background:{bg3} !important;
  color:{txt2} !important;
  border:1px solid {border2} !important;
  border-radius:8px !important;
}}
[data-testid="stFileUploaderDropzone"] small,
[data-testid="stFileUploaderDropzone"] span {{
  color:{txt4} !important;
}}

/* ── Checkbox ──────────────────────────────────────────────────────────── */
[data-baseweb="checkbox"] > div:first-child {{
  background:{input_bg} !important;
  border-color:{border3} !important;
  border-radius:5px !important;
}}
[data-testid="stCheckbox"] label p {{ color:{txt3} !important; }}

/* ── Bordered containers (st.container(border=True)) ──────────────────── */
[data-testid="stVerticalBlockBorderWrapper"] {{
  border-radius:12px !important;
}}
[data-testid="stVerticalBlockBorderWrapper"] > div {{ border-color:{border2} !important; }}

/* ── Main content area text ────────────────────────────────────────────── */
.main [data-testid="stMarkdownContainer"] p {{ color:{txt3} !important; }}
.main label {{ color:{lbl_color} !important; }}

/* ── Toggle ────────────────────────────────────────────────────────────── */
[data-testid="stToggle"] label p, [data-testid="stWidgetLabel"] p {{
  color:{txt3} !important;
}}
[data-testid="stSidebar"] [data-testid="stToggle"] label p {{
  font-size:0.85rem !important; color:{txt4} !important;
}}

/* ── Page header — level 1 of the hierarchy ────────────────────────────── */
.rv-head {{ margin:0 0 20px; }}
.rv-head h1 {{
  font-family:'Plus Jakarta Sans',sans-serif; font-weight:700; font-size:1.75rem;
  letter-spacing:-0.025em; line-height:1.2; color:{h1_color}; margin:0 0 6px;
}}
.rv-head .rv-sub {{ font-size:0.9375rem; color:{txt3}; margin:0; line-height:1.55; }}

/* ── Status chips — level 3, quiet by design ───────────────────────────── */
.rv-chips {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:0 0 16px; }}
.rv-chip {{
  display:inline-flex; align-items:center; gap:6px;
  background:{bg3}; border:1px solid {border2}; color:{txt3};
  border-radius:999px; padding:5px 12px; font-size:0.8125rem;
  font-weight:500; line-height:1.3; white-space:nowrap;
}}
.rv-chip.on  {{ background:rgba(245,158,11,0.12); border-color:rgba(245,158,11,0.38); color:{accent_txt}; }}
.rv-chip.ok  {{ background:rgba(16,185,129,0.12); border-color:rgba(16,185,129,0.35);
                color:{"#6EE7B7" if is_dark else "#047857"}; }}
.rv-chip .rv-dot {{ width:6px; height:6px; border-radius:50%; background:currentColor; flex:none; }}

/* ── Sidebar connection summary ────────────────────────────────────────── */
.rv-conn {{
  display:flex; align-items:center; justify-content:space-between; gap:8px;
  background:{bg3}; border:1px solid {border2}; border-radius:10px;
  padding:9px 12px; margin:0 0 4px;
}}
.rv-conn-l {{ font-size:0.8125rem; color:{txt3}; font-weight:500; }}
.rv-conn-v {{ font-size:0.8125rem; font-weight:700; letter-spacing:-0.01em; }}

/* ── Chat empty state ──────────────────────────────────────────────────── */
.rv-hero {{ text-align:center; padding:48px 0 4px; }}
@media (max-height: 700px) {{ .rv-hero {{ padding-top:16px; }} }}
.rv-hero .rv-spark {{
  width:52px; height:52px; margin:0 auto 16px; border-radius:14px;
  display:flex; align-items:center; justify-content:center; font-size:24px;
  background:rgba(245,158,11,0.12); border:1px solid rgba(245,158,11,0.3);
}}
.rv-hero h2 {{
  font-family:'Plus Jakarta Sans',sans-serif; font-weight:700; font-size:1.5rem;
  letter-spacing:-0.025em; color:{txt1}; margin:0 0 8px;
}}
.rv-hero p {{ font-size:0.9375rem; color:{txt3}; margin:0; line-height:1.6; }}
.rv-ctx {{
  font-size:0.8125rem; color:{txt4}; margin:0 0 8px; font-weight:500;
}}

/* Suggestion buttons under the composer — quiet until hovered, so they read as
   optional shortcuts rather than four competing calls to action. */
.st-key-rv_sugg [data-testid="stBaseButton-secondary"] {{
  background:{bg3} !important; border:1px solid {border2} !important;
  color:{txt3} !important; border-radius:999px !important;
  font-weight:500 !important; padding:8px 16px !important;
  box-shadow:none !important; min-height:40px !important;
}}
.st-key-rv_sugg [data-testid="stBaseButton-secondary"]:hover {{
  border-color:rgba(245,158,11,0.5) !important; color:{accent_txt} !important;
  background:{bg2} !important;
}}

/* Chat composer — the primary control on the page, so it gets the accent ring
   on focus and enough height to read as an input rather than a search box. */
[data-testid="stChatInput"] {{ box-shadow:{card_shadow} !important; }}
[data-testid="stChatInput"]:focus-within {{
  border-color:rgba(245,158,11,0.55) !important;
  box-shadow:0 0 0 3px rgba(245,158,11,0.12) !important;
}}
[data-testid="stBottomBlockContainer"] {{
  max-width:1180px !important; margin:0 auto !important; padding-bottom:1.25rem !important;
}}

/* Mobile: the sidebar overlays, so the content needs its own breathing room and
   the suggestion row has to be allowed to wrap instead of squeezing to 3 columns
   of 90px each. */
@media (max-width: 640px) {{
  .block-container {{ padding-left:1rem !important; padding-right:1rem !important; }}
  .rv-head h1 {{ font-size:1.4rem !important; }}
  .rv-hero h2 {{ font-size:1.25rem !important; }}
  h1 {{ font-size:1.4rem !important; }}
}}
</style>
""", unsafe_allow_html=True)


st.set_page_config(
    page_title="REVENUE AI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Theme initialisation — must happen before any st.* call other than set_page_config
#
# Defaults to light so the components match the app frame. Streamlit paints that
# frame — background, sidebar, header — from config.toml, and in this version
# nothing injected at runtime overrides it (tested: higher specificity, layered
# and unlayered !important, even an inline style). A dark default therefore
# produced dark buttons and cards sitting inside a light window.
if "theme" not in st.session_state:
    st.session_state["theme"] = "light"
_theme = st.session_state["theme"]
_chart_tpl = "premium_light" if _theme == "light" else "premium_dark"
pio.templates.default = _chart_tpl
px.defaults.template = _chart_tpl
apply_premium_theme(_theme)


def _chart(fig: go.Figure, stretch: bool = True, **kw) -> None:
    """Render a Plotly chart with correct theme colours, bypassing Streamlit's override."""
    if _theme == "light":
        fig.update_layout(
            paper_bgcolor="#FFFFFF",
            plot_bgcolor="#F8F7F4",
            font=dict(color="#6B7280"),
            xaxis=dict(gridcolor="rgba(0,0,0,0.06)", tickfont=dict(color="#9CA3AF")),
            yaxis=dict(gridcolor="rgba(0,0,0,0.06)", tickfont=dict(color="#9CA3AF")),
            legend=dict(bgcolor="rgba(255,255,255,0.95)", font=dict(color="#6B7280")),
            hoverlabel=dict(bgcolor="#FFFFFF", font=dict(color="#111827")),
            title=dict(font=dict(color="#111827")),
        )
    st.plotly_chart(fig, width="stretch" if stretch else "content", theme=None, **kw)


# ── Shared UI primitives ───────────────────────────────────────────────────────
#
# Three levels, applied on every page:
#   1. _page_head   — what this page is, and what it is for
#   2. the workspace itself
#   3. _chips       — status and secondary detail, deliberately quiet
#
# Before this, each page invented its own header: some had a title and a caption,
# some added a row of coloured pills that competed with the primary action, some
# put the AI provider label in a right-hand column where it read as a heading.

def _set_theme(t: str) -> None:
    """Theme switch as an on_click callback, never `if st.button(): st.rerun()`.

    A mid-run st.rerun() aborts before the widgets below it are instantiated, so
    Streamlit drops their keyed state and the app jumps back to the first page.
    A callback sets the theme before the natural rerun, keeping the page sticky.
    """
    st.session_state["theme"] = t


def _esc(s: str) -> str:
    """Minimal escape — these strings are ours, but they carry user brand names."""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _page_head(title: str, subtitle: str = "") -> None:
    sub = f'<p class="rv-sub">{_esc(subtitle)}</p>' if subtitle else ""
    st.markdown(f'<div class="rv-head"><h1>{_esc(title)}</h1>{sub}</div>',
                unsafe_allow_html=True)


def _chips(items: list[tuple[str, str]]) -> None:
    """A row of status chips. Each item is (label, tone) — tone in "", "on", "ok"."""
    if not items:
        return
    html = "".join(
        f'<span class="rv-chip {tone}">{"<span class=rv-dot></span>" if tone else ""}'
        f'{_esc(label)}</span>'
        for label, tone in items
    )
    st.markdown(f'<div class="rv-chips">{html}</div>', unsafe_allow_html=True)


# ── Settings storage ───────────────────────────────────────────────────────────
#
# Tokens used to live in sidebar widgets, so their values only existed while the
# sidebar rendered them — which is why every page had to be handed six token
# arguments. Keying them into session_state lets the Settings and Integrations
# pages own the forms while every other page reads the same values.

K_LINE   = "set_line_token"
K_FB     = "set_fb_token"
K_FB_PID = "set_fb_page_id"
K_IG     = "set_ig_business_id"
K_TIKTOK = "tiktok_token"      # pre-existing key — tiktok_poster reads it directly
K_AI     = "set_ai_mode"
K_GEMINI = "set_gemini_key"
K_CLAUDE = "set_claude_key"
K_LV     = "set_lv_token"
K_LV_DAY = "set_lv_days"
K_FB_APP = "set_fb_app_id"
K_FB_SEC = "set_fb_app_secret"


def _load_saved_settings() -> None:
    """Seed session state from disk, once per session.

    setdefault, not assignment: a value already in session_state came from the
    person using the app right now and must outrank whatever was saved earlier.
    """
    if st.session_state.get("_settings_loaded") or not SECRETS_STORE_AVAILABLE:
        return
    for key, value in secrets_store.load().items():
        st.session_state.setdefault(key, value)
    st.session_state["_settings_loaded"] = True


def _s(key: str, default: str = "") -> str:
    return st.session_state.get(key, default) or default


# Widget state is not storage.
#
# Streamlit drops a keyed widget's session_state entry on the first run where
# that widget is not instantiated. With the forms living on Settings and
# Integrations, that means every token evaporates the moment someone navigates
# to the queue to post — which is the one place they are needed. Found by
# watching a Gemini key survive on its own page and be gone one click later.
#
# So the value lives under a plain key nothing else claims, and the widget gets
# a separate `w_`-prefixed key it is free to lose. The widget writes back on
# change; the rest of the app only ever reads the plain key.

def _commit_setting(store_key: str, widget_key: str) -> None:
    st.session_state[store_key] = st.session_state.get(widget_key)


def _stage_settings(values: dict) -> None:
    """Queue values for the next run, for code that fills a field on the user's
    behalf (picking a Facebook page, say).

    Writing the store key alone is not enough. The widget on screen still holds
    its old text, and on the next run its on_change fires and writes that stale
    text straight back over what was just set — which looked exactly like the
    assignment never happening. Writing the widget key too would fix it, but
    Streamlit refuses that once the widget exists this run. So it waits.
    """
    st.session_state["_pending_settings"] = {
        **st.session_state.get("_pending_settings", {}), **values}


def _apply_pending_settings() -> None:
    """Drain the queue. Must run before any settings widget is instantiated."""
    pending = st.session_state.pop("_pending_settings", None)
    if not pending:
        return
    for key, value in pending.items():
        st.session_state[key] = value
        st.session_state["w_" + key] = value


def _setting_text(label: str, store_key: str, *, password: bool = False,
                  **kw) -> str:
    wk = "w_" + store_key
    st.text_input(label, value=_s(store_key), key=wk,
                  type="password" if password else "default",
                  on_change=_commit_setting, args=(store_key, wk), **kw)
    return _s(store_key)


def _setting_radio(label: str, options: list[str], store_key: str,
                   default: str = "", **kw) -> str:
    wk = "w_" + store_key
    current = _s(store_key, default or options[0])
    index = options.index(current) if current in options else 0
    st.radio(label, options, index=index, key=wk,
             on_change=_commit_setting, args=(store_key, wk), **kw)
    return _s(store_key, default or options[0])


def _setting_select(label: str, options: list, store_key: str, default=None,
                    **kw):
    wk = "w_" + store_key
    current = st.session_state.get(store_key, default if default is not None
                                   else options[0])
    index = options.index(current) if current in options else 0
    st.selectbox(label, options, index=index, key=wk,
                 on_change=_commit_setting, args=(store_key, wk), **kw)
    return st.session_state.get(store_key, options[index])


def _setting_slider(label: str, lo: int, hi: int, store_key: str,
                    default: int, **kw) -> int:
    wk = "w_" + store_key
    st.slider(label, lo, hi, value=int(st.session_state.get(store_key, default)),
              key=wk, on_change=_commit_setting, args=(store_key, wk), **kw)
    return int(st.session_state.get(store_key, default))


def _resolve_api_key(ai_mode: str) -> str:
    if ai_mode == "Gemini API":
        return _s(K_GEMINI)
    if ai_mode == "Claude API":
        return _s(K_CLAUDE)
    return ""


@st.cache_data(ttl=300, show_spinner=False)
def _drive_ready() -> bool:
    """needs_auth() reads a token file and may refresh it over the network.

    The sidebar asks on every rerun — including every keystroke-triggered one —
    so the answer is cached. Five minutes is well inside a token's lifetime.
    """
    return bool(GDRIVE_AVAILABLE and not needs_auth())


def _connection_status() -> list[tuple[str, bool]]:
    """(channel name, connected) for every channel the app can post through."""
    fb = bool(_s(K_FB) and _s(K_FB_PID))
    drive = _drive_ready()
    return [
        ("LINE OA", bool(_s(K_LINE))),
        ("Facebook", fb),
        ("Instagram", bool(_s(K_FB) and _s(K_IG))),
        ("TikTok", bool(_s(K_TIKTOK))),
        ("Google Drive", drive),
    ]


# Before anything reads a token — the sidebar's connection count is the first
# thing to ask, and it runs before either settings page exists.
_load_saved_settings()


DATA_PATH = Path("data/sample_transactions.csv")
YENTAFO_DIR = Path("data/client-yentafo")


# ── Data generation ────────────────────────────────────────────────────────────

def generate_sample_data(rows: int = 2500) -> pd.DataFrame:
    np.random.seed(42)
    now = dt.datetime.now()
    start = now - dt.timedelta(days=90)
    branches = ["Siam", "Ari", "Thonglor"]
    staff = ["Nok", "Mek", "Ploy", "Bank", "Jane", "Tum"]
    items = ["Signature Latte", "Craft Beer", "Protein Shake", "Classic Burger", "Set Menu", "Cocktail"]
    segments = ["new", "active", "at_risk"]
    records = []
    for i in range(rows):
        order_time = start + dt.timedelta(minutes=np.random.randint(0, int((now - start).total_seconds() // 60)))
        branch = np.random.choice(branches, p=[0.4, 0.3, 0.3])
        customer_id = f"C{np.random.randint(1, 700):04d}"
        customer_segment = np.random.choice(segments, p=[0.20, 0.50, 0.30])
        item = np.random.choice(items)
        qty = np.random.choice([1, 1, 1, 2, 2, 3])
        base_price = np.random.choice([90, 120, 150, 180, 220, 260])
        discount = np.random.choice([0, 0, 10, 20, 30])
        gross = base_price * qty
        net = max(gross - discount, 50)
        cost = round(net * np.random.uniform(0.38, 0.62), 2)
        margin = round(net - cost, 2)
        staff_name = np.random.choice(staff)
        records.append({
            "order_id": f"O{i+1:05d}", "order_time": order_time,
            "branch": branch, "staff": staff_name,
            "customer_id": customer_id, "customer_segment": customer_segment,
            "item": item, "qty": qty, "gross": gross,
            "discount": discount, "net_sales": net, "cost": cost, "margin": margin,
        })
    df = pd.DataFrame(records)
    df["order_time"] = pd.to_datetime(df["order_time"])
    return df.sort_values("order_time")


def generate_mookrata_data(rows: int = 3000) -> pd.DataFrame:
    np.random.seed(7)
    now = dt.datetime.now()
    start = now - dt.timedelta(days=90)
    branches = ["ลาดพร้าว", "บางนา", "รัชดา"]
    staff = ["เอ", "บี", "ซี", "ดี", "ออม", "นัท", "มุก", "ต้น"]
    ala_items = ["ชุดหมูรวม", "ชุดเนื้อรวม", "ซีฟู้ดรวม", "หมูสไลซ์", "ชีสยืด", "น้ำจิ้มสูตรเด็ด"]
    segments = ["new", "active", "at_risk"]
    records = []
    for i in range(rows):
        day_offset = np.random.randint(0, 90)
        hour = np.random.choice(
            [11, 12, 13, 17, 18, 19, 20, 21, 22],
            p=[0.03, 0.05, 0.05, 0.12, 0.2, 0.22, 0.18, 0.1, 0.05],
        )
        minute = np.random.randint(0, 60)
        order_time = (start + dt.timedelta(days=day_offset)).replace(hour=hour, minute=minute)
        branch = np.random.choice(branches, p=[0.45, 0.3, 0.25])
        customer_segment = np.random.choice(segments, p=[0.22, 0.5, 0.28])
        customer_id = f"M{np.random.randint(1, 900):04d}"
        staff_name = np.random.choice(staff)
        service_type = np.random.choice(["buffet", "alacarte"], p=[0.58, 0.42])
        if service_type == "buffet":
            item = np.random.choice(["บุฟเฟ่ต์ผู้ใหญ่", "บุฟเฟ่ต์เด็ก", "บุฟเฟ่ต์พรีเมียม"], p=[0.68, 0.08, 0.24])
            qty = np.random.choice([1, 2, 2, 3, 4])
            base_price = np.random.choice([199, 239, 299, 359], p=[0.35, 0.35, 0.2, 0.1])
            discount = np.random.choice([0, 0, 20, 30, 40], p=[0.55, 0.2, 0.12, 0.08, 0.05])
        else:
            item = np.random.choice(ala_items)
            qty = np.random.choice([1, 1, 2, 2, 3, 4])
            base_price = np.random.choice([69, 89, 119, 149, 179, 219])
            discount = np.random.choice([0, 0, 10, 20], p=[0.65, 0.2, 0.1, 0.05])
        gross = base_price * qty
        net = max(gross - discount, 50)
        cost_ratio = np.random.uniform(0.43, 0.66) if service_type == "buffet" else np.random.uniform(0.35, 0.58)
        cost = round(net * cost_ratio, 2)
        margin = round(net - cost, 2)
        records.append({
            "order_id": f"MOO{i+1:05d}", "order_time": order_time,
            "branch": branch, "staff": staff_name,
            "customer_id": customer_id, "customer_segment": customer_segment,
            "service_type": service_type, "item": item, "qty": qty, "gross": gross,
            "discount": discount, "net_sales": net, "cost": cost, "margin": margin,
        })
    df = pd.DataFrame(records)
    df["order_time"] = pd.to_datetime(df["order_time"])
    return df.sort_values("order_time")


def load_data() -> pd.DataFrame:
    if DATA_PATH.exists():
        df = pd.read_csv(DATA_PATH)
        df["order_time"] = pd.to_datetime(df["order_time"])
        return df
    df = generate_sample_data()
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(DATA_PATH, index=False)
    return df


def load_yentafo_aggregates(base_dir: Path) -> dict[str, pd.DataFrame]:
    data: dict[str, pd.DataFrame] = {
        "hourly": pd.DataFrame(), "weekday": pd.DataFrame(),
        "order_type": pd.DataFrame(), "channel": pd.DataFrame(),
        "hour_by_weekday": pd.DataFrame(),
    }
    if not base_dir.exists():
        return data
    files = sorted(base_dir.glob("*.xlsx")) + sorted(base_dir.glob("*.xls"))
    for file in files:
        if file.name.startswith("~$"):
            continue
        try:
            xls = pd.ExcelFile(file)
        except (PermissionError, Exception):
            continue
        for sheet in xls.sheet_names:
            df = xls.parse(sheet)
            if df.empty:
                continue
            df.columns = [str(c).strip() for c in df.columns]
            lower_cols = {c.lower() for c in df.columns}
            sheet_lower = sheet.lower()
            if {"ordertype", "sales", "orders"}.issubset(lower_cols):
                data["order_type"] = df.copy()
            elif {"dayofweek", "sales", "orders"}.issubset(lower_cols):
                data["weekday"] = df.copy()
            elif {"time", "sales", "orders"}.issubset(lower_cols):
                channel_df = df.copy()
                channel_df["channel"] = sheet
                data["channel"] = pd.concat([data["channel"], channel_df], ignore_index=True)
            elif {"hour", "daycount", "sales", "orders"}.issubset(lower_cols):
                if sheet_lower in {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}:
                    weekday_hour = df.copy()
                    weekday_hour["weekday"] = sheet
                    data["hour_by_weekday"] = pd.concat([data["hour_by_weekday"], weekday_hour], ignore_index=True)
                else:
                    data["hourly"] = df.copy()
    return data


# ── AI Insights ────────────────────────────────────────────────────────────────

def get_ai_insights_local(df: pd.DataFrame) -> list[str]:
    insights = []

    # Revenue trend: recent 30 days vs prior 30 days
    now = df["order_time"].max()
    recent_rev = df[df["order_time"] >= now - dt.timedelta(days=30)]["net_sales"].sum()
    prev_rev = df[
        (df["order_time"] >= now - dt.timedelta(days=60)) &
        (df["order_time"] < now - dt.timedelta(days=30))
    ]["net_sales"].sum()
    if prev_rev > 0:
        trend = (recent_rev - prev_rev) / prev_rev
        if trend > 0.02:
            insights.append(f"📈 ยอดขาย 30 วันล่าสุดโต {trend:.1%} จากเดือนก่อน — momentum ดี ลองดัน upsell ตอนนี้")
        elif trend < -0.02:
            insights.append(f"📉 ยอดขาย 30 วันล่าสุดลด {abs(trend):.1%} — ควรเปิด retention campaign ทันที")

    # Weak vs peak hours
    by_hour = df.groupby(df["order_time"].dt.hour)["net_sales"].sum()
    weak_hours = sorted(by_hour.nsmallest(3).index.tolist())
    peak_hours = sorted(by_hour.nlargest(2).index.tolist())
    insights.append(f"⏰ ช่วงยอดต่ำ: {', '.join(f'{h:02d}:00' for h in weak_hours)} → เปิด Flash Sale หรือ Happy Hour")
    insights.append(f"🔥 ช่วงพีค: {', '.join(f'{h:02d}:00' for h in peak_hours)} → เพิ่มพนักงาน + ดัน Upsell")

    # At-risk customers
    if "customer_segment" in df.columns:
        seg = df.groupby("customer_segment")["customer_id"].nunique()
        at_risk = seg.get("at_risk", 0)
        total = seg.sum()
        if total > 0:
            pct = at_risk / total
            if pct > 0.2:
                insights.append(f"⚠️ ลูกค้าเสี่ยงหาย {pct:.1%} ({at_risk:,} คน) → เปิด Win-back Campaign ทันที")
            else:
                insights.append(f"✅ ลูกค้าเสี่ยงหาย {pct:.1%} — ระดับปกติ ควรมี automated follow-up ทุก 14 วัน")

    # Top margin item
    if "item" in df.columns:
        top_item = df.groupby("item")["margin"].sum().idxmax()
        top_margin = df.groupby("item")["margin"].sum().max()
        insights.append(f"⭐ '{top_item}' สร้าง margin สูงสุด ฿{top_margin:,.0f} → ดันเป็น Hero Product")

    # Branch gap
    if "branch" in df.columns and df["branch"].nunique() > 1:
        by_branch = df.groupby("branch")["margin"].sum()
        best_b = by_branch.idxmax()
        worst_b = by_branch.idxmin()
        gap = (by_branch[best_b] - by_branch[worst_b]) / by_branch[best_b]
        insights.append(f"🏪 สาขา '{best_b}' margin ดีกว่า '{worst_b}' ถึง {gap:.1%} → ศึกษา best practice แล้ว replicate")

    return insights


def get_ai_insights_claude(df: pd.DataFrame, api_key: str) -> list[str]:
    if not ANTHROPIC_AVAILABLE:
        return ["❌ ต้องติดตั้ง anthropic ก่อน: pip install anthropic"]
    try:
        client = anthropic.Anthropic(api_key=api_key)

        now = df["order_time"].max()
        recent_rev = df[df["order_time"] >= now - dt.timedelta(days=30)]["net_sales"].sum()
        prev_rev = df[
            (df["order_time"] >= now - dt.timedelta(days=60)) &
            (df["order_time"] < now - dt.timedelta(days=30))
        ]["net_sales"].sum()
        trend_pct = (recent_rev - prev_rev) / prev_rev * 100 if prev_rev > 0 else 0

        context = {
            "summary": {
                "total_revenue": round(float(df["net_sales"].sum()), 0),
                "total_margin": round(float(df["margin"].sum()), 0),
                "aov": round(float(df["net_sales"].mean()), 0),
                "transactions": int(len(df)),
                "revenue_trend_30d_pct": round(trend_pct, 1),
            },
            "customer_segments": (
                df.groupby("customer_segment")["customer_id"].nunique().to_dict()
                if "customer_segment" in df.columns else {}
            ),
            "hourly_revenue": {
                f"{h:02d}:00": round(float(v), 0)
                for h, v in df.groupby(df["order_time"].dt.hour)["net_sales"].sum().items()
            },
            "top_items_by_margin": (
                {k: round(float(v), 0) for k, v in df.groupby("item")["margin"].sum().nlargest(5).items()}
                if "item" in df.columns else {}
            ),
            "branch_revenue": (
                {k: round(float(v), 0) for k, v in df.groupby("branch")["net_sales"].sum().items()}
                if "branch" in df.columns else {}
            ),
        }

        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            system=[{
                "type": "text",
                "text": (
                    "คุณเป็น AI Business Analyst ที่มีประสบการณ์ทำงานเป็น CFO และ CMO "
                    "ในธุรกิจร้านอาหาร คาเฟ่ และ F&B ไทยมาก่อน "
                    "วิเคราะห์ข้อมูลแล้วให้ insights ที่ actionable จริงๆ "
                    "แต่ละ insight ต้องระบุ: 1) fact จากตัวเลข 2) action ที่ทำได้ภายใน 24-48 ชม. "
                    "3) expected impact ที่วัดได้ "
                    "ห้ามพูด generic เช่น 'ควรปรับปรุง' หรือ 'ควรวิเคราะห์เพิ่มเติม' "
                    "ตอบเป็นภาษาไทย สั้นกระชับ ไม่เกิน 2 ประโยคต่อ insight"
                ),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": (
                    f"ข้อมูลธุรกิจ:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
                    "ให้ 5 insights ที่ actionable ที่สุด ห้ามซ้ำกัน\n"
                    "ตอบในรูปแบบ JSON array เท่านั้น: [\"insight 1\", \"insight 2\", ...]"
                ),
            }],
        )
        text = message.content[0].text.strip()
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return [text]
    except Exception as e:
        return [f"❌ Claude API Error: {e}", "💡 ลองเช็ค API key หรือเปลี่ยนกลับ Local mode"]


def get_ai_insights(df: pd.DataFrame, mode: str, api_key: str = "") -> list[str]:
    if mode == "Claude API" and api_key.strip():
        return get_ai_insights_claude(df, api_key.strip())
    return get_ai_insights_local(df)


def get_sales_forecast(df: pd.DataFrame, days: int = 7) -> pd.DataFrame:
    # Group by date
    daily = df.assign(date=df["order_time"].dt.date).groupby("date")["net_sales"].sum().reset_index()
    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily.sort_values("date")

    if len(daily) < 7:
        return pd.DataFrame()

    # Simple Moving Average for trend
    daily["sma_7"] = daily["net_sales"].rolling(window=7).mean()

    # Simple linear trend on the last 14 days
    recent = daily.tail(14)
    x = np.arange(len(recent))
    y = recent["net_sales"].values
    if len(x) > 1:
        slope, intercept = np.polyfit(x, y, 1)
    else:
        slope, intercept = 0, y[0]

    # Project future
    last_date = daily["date"].max()
    future_dates = [last_date + dt.timedelta(days=i) for i in range(1, days + 1)]

    # Forecast calculation (Trend + SMA weight)
    last_sma = daily["sma_7"].iloc[-1]
    forecast_values = []
    for i in range(1, days + 1):
        # Forecast = Last SMA + (slope * i)
        val = max(last_sma + (slope * (i / 2)), 0) # dampened slope
        forecast_values.append(val)

    forecast_df = pd.DataFrame({
        "date": future_dates,
        "net_sales": forecast_values,
        "type": "Forecast"
    })

    # Prepare historical for plotting
    historical_df = daily[["date", "net_sales"]].copy()
    historical_df["type"] = "Actual"

    return pd.concat([historical_df, forecast_df], ignore_index=True)


def content_suggestions(df: pd.DataFrame) -> list[str]:
    by_hour = df.groupby(df["order_time"].dt.hour)["net_sales"].sum()
    weak_hour = int(by_hour.idxmin()) if not by_hour.empty else 15
    top_item = df.groupby("item")["margin"].sum().idxmax() if "item" in df.columns else "เมนูยอดนิยม"
    return [
        f"โปรด่วน {weak_hour:02d}:00-{weak_hour+2:02d}:00 วันนี้: ซื้อ 2 แถม 1 เฉพาะ '{top_item}'",
        "LINE OA: คิดถึงนะ! กลับมาใช้สิทธิ์ลูกค้าประจำวันนี้ รับส่วนลด 15%",
        "IG Story: ช่วงบ่ายจัดโปร time-based เพิ่ม traffic หน้าร้านทันที",
        "Facebook: แชร์ review ลูกค้าจริงพร้อม limited offer เฉพาะวันนี้",
    ]


@st.cache_data
def generate_excel_report(df: pd.DataFrame) -> bytes:
    insights = get_ai_insights_local(df)
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # Sheet 1: KPI Summary
        now = df["order_time"].max()
        recent_rev = df[df["order_time"] >= now - dt.timedelta(days=30)]["net_sales"].sum()
        prev_rev = df[
            (df["order_time"] >= now - dt.timedelta(days=60)) &
            (df["order_time"] < now - dt.timedelta(days=30))
        ]["net_sales"].sum()
        trend = (recent_rev - prev_rev) / prev_rev * 100 if prev_rev > 0 else 0
        repeat = (df["customer_segment"] != "new").mean() if "customer_segment" in df.columns else 0

        pd.DataFrame({
            "Metric": ["Revenue (Total)", "Margin (Total)", "AOV", "Transactions",
                       "Revenue Trend (30d vs prior 30d)", "Repeat Rate"],
            "Value": [
                f"฿{df['net_sales'].sum():,.0f}",
                f"฿{df['margin'].sum():,.0f}",
                f"฿{df['net_sales'].mean():,.0f}",
                f"{len(df):,}",
                f"{trend:+.1f}%",
                f"{repeat:.1%}",
            ],
        }).to_excel(writer, sheet_name="KPI Summary", index=False)

        # Sheet 2: Daily Sales
        (
            df.assign(Date=df["order_time"].dt.date)
            .groupby("Date", as_index=False)
            .agg(Revenue=("net_sales", "sum"), Margin=("margin", "sum"), Transactions=("order_id", "count"))
        ).to_excel(writer, sheet_name="Daily Sales", index=False)

        # Sheet 3: Top Items by Margin
        if "item" in df.columns:
            (
                df.groupby("item", as_index=False)
                .agg(Revenue=("net_sales", "sum"), Margin=("margin", "sum"), Orders=("order_id", "count"))
                .sort_values("Margin", ascending=False)
            ).to_excel(writer, sheet_name="Top Items", index=False)

        # Sheet 4: Branch Performance
        if "branch" in df.columns and df["branch"].nunique() > 1:
            (
                df.groupby("branch", as_index=False)
                .agg(Revenue=("net_sales", "sum"), Margin=("margin", "sum"), Transactions=("order_id", "count"))
                .sort_values("Revenue", ascending=False)
            ).to_excel(writer, sheet_name="Branch Performance", index=False)

        # Sheet 5: Customer Segments
        if "customer_segment" in df.columns:
            (
                df.groupby("customer_segment", as_index=False)
                .agg(Customers=("customer_id", "nunique"), Revenue=("net_sales", "sum"))
            ).to_excel(writer, sheet_name="Customer Segments", index=False)

        # Sheet 6: Hourly Revenue
        (
            df.assign(Hour=df["order_time"].dt.hour)
            .groupby("Hour", as_index=False)
            .agg(Revenue=("net_sales", "sum"), Transactions=("order_id", "count"))
        ).to_excel(writer, sheet_name="Hourly Revenue", index=False)

        # Sheet 7: AI Insights
        pd.DataFrame({
            "#": range(1, len(insights) + 1),
            "Insight & Recommendation": insights,
        }).to_excel(writer, sheet_name="AI Insights", index=False)

    return output.getvalue()


# ── Connect POS Page ───────────────────────────────────────────────────────────

def render_connect_pos_page(lv_token: str, lv_days: int, ai_mode: str, api_key: str) -> None:
    _page_head("🔌 Connect POS — Loyverse", "ดึงข้อมูลยอดขายจริงจาก Loyverse POS เข้าสู่ REVENUE AI")

    with st.expander("วิธีรับ API Token จาก Loyverse", expanded=False):
        st.markdown("""
1. เข้า [Loyverse Back Office](https://r.loyverse.com/dashboard/) (Back Office → Settings)
2. ไปที่ **API access tokens** → **Create new token**
3. ตั้งชื่อ token (เช่น `ai-revenue-intelligence`) แล้ว copy
4. วาง token ในช่องด้านซ้าย แล้วกด **เชื่อมต่อ & ดึงข้อมูล**

Token จะถูกใช้เฉพาะในเซสชั่นนี้เท่านั้น ไม่ถูกบันทึกลงเซิร์ฟเวอร์ใด
        """)

    if not LOYVERSE_AVAILABLE:
        st.error("ไม่พบ loyverse_connector.py — ตรวจสอบว่าไฟล์อยู่ในโฟลเดอร์เดียวกับ app.py")
        return

    if not lv_token:
        st.info("ใส่ Loyverse API Token ในแถบซ้ายเพื่อเริ่มต้น")
        _render_loyverse_demo_preview()
        return

    col_btn, col_status = st.columns([1, 3])
    with col_btn:
        connect_btn = st.button("🔄 เชื่อมต่อ & ดึงข้อมูล")

    if not connect_btn and "loyverse_df" not in st.session_state:
        st.info("กด 'เชื่อมต่อ & ดึงข้อมูล' เพื่อดึงข้อมูลจาก Loyverse")
        return

    if connect_btn:
        with st.spinner("กำลังเชื่อมต่อ Loyverse API..."):
            try:
                connector = LoyverseConnector(lv_token)
                if not connector.test_connection():
                    st.error("Token ไม่ถูกต้องหรือหมดอายุ — ตรวจสอบใน Loyverse Back Office")
                    return

                merchant = connector.get_merchant_info()
                merchant_name = merchant.get("name", "ร้านของคุณ") if merchant else "ร้านของคุณ"

                date_from = dt.datetime.now() - dt.timedelta(days=lv_days)
                with st.spinner(f"ดึงข้อมูล {lv_days} วัน จาก {merchant_name}..."):
                    raw_df = connector.to_standard_df(date_from=date_from)

                if raw_df.empty:
                    st.warning("ไม่พบข้อมูลในช่วงเวลาที่เลือก ลองขยายช่วงวันให้กว้างขึ้น")
                    return

                # Apply RFM segmentation
                rfm_df = compute_rfm(raw_df)
                raw_df = label_transactions(raw_df, rfm_df)

                st.session_state["loyverse_df"] = raw_df
                st.session_state["loyverse_rfm"] = rfm_df
                st.session_state["loyverse_merchant"] = merchant_name
                st.success(f"เชื่อมต่อสำเร็จ: **{merchant_name}** | {len(raw_df):,} รายการ | {raw_df['order_time'].min().date()} ถึง {raw_df['order_time'].max().date()}")
            except Exception as e:
                st.error(f"เชื่อมต่อไม่ได้: {e}")
                return

    if "loyverse_df" not in st.session_state:
        return

    df = st.session_state["loyverse_df"]
    rfm = st.session_state.get("loyverse_rfm", pd.DataFrame())
    merchant_name = st.session_state.get("loyverse_merchant", "ร้านของคุณ")

    st.subheader(f"ข้อมูลจริง: {merchant_name}")

    # KPIs
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Revenue", f"฿{df['net_sales'].sum():,.0f}")
    k2.metric("Margin", f"฿{df['margin'].sum():,.0f}")
    k3.metric("Transactions", f"{len(df):,}")
    k4.metric("Unique Customers", f"{df['customer_id'].nunique():,}")

    tab_sales, tab_rfm, tab_ai = st.tabs(["ยอดขาย", "RFM Segments", "AI Insights"])

    with tab_sales:
        daily = df.assign(date=df["order_time"].dt.date).groupby("date", as_index=False)["net_sales"].sum()
        fig = px.line(daily, x="date", y="net_sales", title=f"ยอดขายรายวัน — {merchant_name}", markers=True)
        _chart(fig)

        if "branch" in df.columns and df["branch"].nunique() > 1:
            by_branch = df.groupby("branch", as_index=False).agg(Revenue=("net_sales", "sum"), Margin=("margin", "sum"), Transactions=("order_id", "count"))
            _chart(px.bar(by_branch, x="branch", y="Revenue", title="Revenue by Branch"))

    with tab_rfm:
        _render_rfm_tab(df, rfm)

    with tab_ai:
        st.subheader(f"AI Insights ({ai_mode})")
        with st.spinner("กำลังวิเคราะห์..."):
            for insight in get_ai_insights(df, ai_mode, api_key):
                st.success(insight)

    st.divider()
    dl_col, _ = st.columns([1, 2])
    with dl_col:
        st.download_button(
            label="📥 Download Report (.xlsx)",
            data=generate_excel_report(df),
            file_name=f"loyverse_{merchant_name}_{dt.datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )


def _render_rfm_tab(df: pd.DataFrame, rfm: pd.DataFrame) -> None:
    """Shared RFM visualisation used in both Connect POS and Customer Intelligence tabs."""
    if rfm.empty:
        rfm = compute_rfm(df)
    if rfm.empty:
        st.warning("ไม่สามารถคำนวณ RFM ได้ — ต้องการข้อมูลอย่างน้อย 10 ลูกค้า")
        return

    summary = rfm_summary(rfm)

    # Treemap
    fig_tree = px.treemap(
        summary,
        path=["segment"],
        values="customers",
        color="total_revenue",
        color_continuous_scale=["#1F2937", "#F59E0B"],
        title="Customer Segments — Treemap (ขนาด = จำนวนลูกค้า, สี = Revenue)",
        custom_data=["avg_recency", "avg_frequency", "avg_monetary", "total_revenue", "action"],
    )
    fig_tree.update_traces(
        hovertemplate=(
            "<b>%{label}</b><br>"
            "ลูกค้า: %{value:,} คน<br>"
            "Revenue รวม: ฿%{customdata[3]:,.0f}<br>"
            "Avg Recency: %{customdata[0]} วัน<br>"
            "Avg Frequency: %{customdata[1]:.1f} ครั้ง<br>"
            "Avg Spend: ฿%{customdata[2]:,.0f}<br>"
            "<b>Action: %{customdata[4]}</b><extra></extra>"
        )
    )
    _chart(fig_tree)

    # Scatter: Frequency vs Monetary coloured by segment
    fig_scatter = px.scatter(
        rfm,
        x="frequency",
        y="monetary",
        color="segment",
        color_discrete_map={s: m["color"] for s, m in SEGMENT_META.items()},
        size="rfm_total",
        title="Customer Scatter — Frequency vs Lifetime Value",
        labels={"frequency": "จำนวนครั้งที่ซื้อ", "monetary": "Lifetime Value (฿)"},
        hover_data=["customer_id", "recency_days", "rfm_score"],
    )
    fig_scatter.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    _chart(fig_scatter)

    # Action table
    st.subheader("Action Plan ตาม Segment")
    for _, row in summary.iterrows():
        seg = row["segment"]
        meta = SEGMENT_META.get(seg, {})
        color = meta.get("color", "#6B7280")
        st.markdown(
            f'<div style="border-left:3px solid {color};padding:0.6rem 1rem;margin-bottom:0.5rem;'
            f'background:rgba(255,255,255,0.02);border-radius:0 8px 8px 0;">'
            f'<strong style="color:{color};">{seg}</strong> '
            f'<span style="color:#6B7280;font-size:0.8rem;">({row["customers"]:,} คน | ฿{row["total_revenue"]:,.0f})</span><br>'
            f'<span style="color:#9CA3AF;font-size:0.875rem;">{meta.get("action","")}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )


def _render_loyverse_demo_preview() -> None:
    st.divider()
    st.markdown("**ตัวอย่างข้อมูลที่จะได้เมื่อเชื่อมต่อ Loyverse:**")
    c1, c2, c3 = st.columns(3)
    c1.info("**ยอดขายรายวัน** แยกสาขา แยก shift")
    c2.info("**RFM Segmentation** Champions / At Risk / Lost ฯลฯ")
    c3.info("**AI Win-back Trigger** อัตโนมัติเมื่อลูกค้าหาย 14 วัน")


# ── CSV Upload Page ─────────────────────────────────────────────────────────────

def render_csv_upload_page(ai_mode: str, api_key: str) -> None:
    _page_head("📁 อัปโหลดข้อมูลของคุณ", "ทดลองวิเคราะห์กับข้อมูล POS จริงของธุรกิจคุณ")

    with st.expander("ดูรูปแบบ CSV ที่รองรับ", expanded=False):
        st.markdown("""
**คอลัมน์บังคับ:**
| คอลัมน์ | ตัวอย่าง |
|---|---|
| `order_id` | O00001 |
| `order_time` | 2026-01-15 18:30:00 |
| `net_sales` | 350 |
| `customer_id` | C0042 |

**คอลัมน์เสริม (ถ้ามีจะวิเคราะห์ได้ลึกขึ้น):**
`branch`, `staff`, `item`, `margin`, `customer_segment` (new/active/at_risk)
        """)
        sample = pd.DataFrame({
            "order_id": ["O00001", "O00002"],
            "order_time": ["2026-01-15 18:30:00", "2026-01-15 19:15:00"],
            "net_sales": [350, 220],
            "customer_id": ["C0042", "C0010"],
            "branch": ["สาขาหลัก", "สาขาหลัก"],
            "item": ["Set Menu", "Latte"],
            "margin": [140, 88],
            "customer_segment": ["active", "new"],
        })
        st.dataframe(sample)

    uploaded = st.file_uploader("เลือกไฟล์ CSV", type=["csv"])

    if "uploaded_df" in st.session_state and uploaded is None:
        st.info("ใช้ข้อมูลที่อัปโหลดครั้งก่อน — อัปโหลดไฟล์ใหม่เพื่อเปลี่ยน")
        _render_upload_analysis(st.session_state["uploaded_df"], ai_mode, api_key)
        return

    if uploaded is not None:
        try:
            df_up = pd.read_csv(uploaded)
            required = {"order_id", "order_time", "net_sales", "customer_id"}
            missing = required - set(df_up.columns)
            if missing:
                st.error(f"ไม่พบคอลัมน์: {', '.join(missing)}")
                return
            df_up["order_time"] = pd.to_datetime(df_up["order_time"], errors="coerce")
            df_up = df_up.dropna(subset=["order_time"])
            if df_up.empty:
                st.error("ไม่พบข้อมูลที่อ่านได้ในไฟล์นี้")
                return
            if "branch" not in df_up.columns:
                df_up["branch"] = "สาขาหลัก"
            if "margin" not in df_up.columns:
                df_up["margin"] = (df_up["net_sales"] * 0.35).round(2)
            if "customer_segment" not in df_up.columns:
                df_up["customer_segment"] = "active"
            if "item" not in df_up.columns:
                df_up["item"] = "สินค้า"
            st.session_state["uploaded_df"] = df_up
            st.success(f"โหลดข้อมูลสำเร็จ: {len(df_up):,} รายการ | {df_up['order_time'].min().date()} ถึง {df_up['order_time'].max().date()}")
            _render_upload_analysis(df_up, ai_mode, api_key)
        except Exception as e:
            st.error(f"อ่านไฟล์ไม่ได้: {e}")


def _render_upload_analysis(df: pd.DataFrame, ai_mode: str, api_key: str) -> None:
    st.divider()
    sales = df["net_sales"].sum()
    margin = df["margin"].sum()
    aov = df["net_sales"].mean()
    repeat = (df["customer_segment"] != "new").mean() if "customer_segment" in df.columns else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Revenue", f"฿{sales:,.0f}")
    k2.metric("Margin", f"฿{margin:,.0f}")
    k3.metric("AOV", f"฿{aov:,.0f}")
    k4.metric("Repeat Rate", f"{repeat:.1%}")

    tab1, tab2 = st.tabs(["ยอดขายรายวัน", "AI Insights"])
    with tab1:
        daily = df.assign(date=df["order_time"].dt.date).groupby("date", as_index=False)["net_sales"].sum()
        fig = px.line(daily, x="date", y="net_sales", title="ยอดขายรายวัน (ข้อมูลของคุณ)", markers=True)
        _chart(fig)
    with tab2:
        st.subheader("AI Insights สำหรับธุรกิจของคุณ")
        with st.spinner("กำลังวิเคราะห์..."):
            for insight in get_ai_insights(df, ai_mode, api_key):
                st.success(insight)


# ── ROI Calculator ──────────────────────────────────────────────────────────────

def render_roi_calculator() -> None:
    _page_head("🧮 ROI Calculator", "คำนวณผลตอบแทนที่คาดได้จากการใช้ระบบ AI for Business")

    col1, col2 = st.columns([1, 1], gap="large")

    with col1:
        st.subheader("ข้อมูลธุรกิจปัจจุบัน")
        monthly_revenue = st.number_input(
            "ยอดขายต่อเดือน (บาท)", min_value=10_000, max_value=10_000_000,
            value=500_000, step=10_000, format="%d",
        )
        current_repeat = st.slider("Repeat Rate ปัจจุบัน (%)", 0, 100, 30)
        avg_margin_pct = st.slider("Margin เฉลี่ย (%)", 10, 80, 35)
        num_branches = st.number_input("จำนวนสาขา", min_value=1, max_value=50, value=1, step=1)
        hours_report = st.slider("ชั่วโมงทำรายงาน/เดือน", 0, 200, 40)
        hourly_rate = st.number_input("ค่าแรงเฉลี่ย (บาท/ชม.)", min_value=50, max_value=1000, value=150, step=50)

    with col2:
        st.subheader("ผลลัพธ์ที่คาดได้")

        repeat_gain_pct = 10
        waste_reduction = 0.15
        report_saving = 0.8

        new_repeat = current_repeat + repeat_gain_pct
        repeat_revenue = monthly_revenue * repeat_gain_pct / 100
        waste_saving = monthly_revenue * avg_margin_pct / 100 * waste_reduction
        labor_saving = hours_report * hourly_rate * report_saving

        monthly_gain = repeat_revenue + waste_saving + labor_saving
        annual_gain = monthly_gain * 12

        if num_branches <= 1:
            setup_cost, monthly_cost, pkg_name = 45_000, 12_000, "Base Analytics"
        elif num_branches <= 3:
            setup_cost, monthly_cost, pkg_name = 95_000, 28_000 * num_branches, "Growth Automation"
        else:
            setup_cost, monthly_cost, pkg_name = 180_000, 55_000 * num_branches, "Scale & Control Tower"

        annual_cost = setup_cost + monthly_cost * 12
        net_roi = annual_gain - annual_cost
        roi_pct = net_roi / annual_cost * 100 if annual_cost > 0 else 0
        payback = annual_cost / monthly_gain if monthly_gain > 0 else 999

        m1, m2 = st.columns(2)
        m1.metric("รายได้เพิ่มจาก Repeat Rate", f"฿{repeat_revenue:,.0f}/เดือน", f"+{repeat_gain_pct}%")
        m2.metric("ประหยัด Waste/Cost", f"฿{waste_saving:,.0f}/เดือน", f"-{waste_reduction:.0%}")
        m3, m4 = st.columns(2)
        m3.metric("ประหยัดเวลารายงาน", f"฿{labor_saving:,.0f}/เดือน", f"-{report_saving:.0%} ชั่วโมง")
        m4.metric("Payback Period", f"{payback:.1f} เดือน")

        st.divider()
        if net_roi > 0:
            st.success(f"**ROI ปีแรก (สุทธิ): ฿{net_roi:,.0f} ({roi_pct:.0f}%)**")
            st.info(f"ลงทุน ฿{annual_cost:,.0f}/ปี → ได้คืน ฿{annual_gain:,.0f}/ปี")
        else:
            st.warning(f"ROI ติดลบปีแรก: ฿{net_roi:,.0f} — ลองปรับค่า input หรือเลือกแพ็กเกจเล็กกว่า")

        st.markdown(f"**แพ็กเกจแนะนำ:** {pkg_name}")
        st.caption(f"Setup ฿{setup_cost:,.0f} + ฿{monthly_cost:,.0f}/เดือน")

    st.divider()
    st.markdown("**สมมติฐานที่ใช้คำนวณ** (อิงจาก case studies ลูกค้าจริง)")
    c1, c2, c3 = st.columns(3)
    c1.info(f"Repeat Rate เพิ่ม +{repeat_gain_pct}%")
    c2.info(f"Waste/Overstock ลด {waste_reduction:.0%}")
    c3.info(f"เวลาทำรายงานลด {report_saving:.0%}")


# ── Yentafo Dashboard (unchanged) ──────────────────────────────────────────────

def render_yentafo_dashboard(y_data: dict[str, pd.DataFrame]) -> None:
    hourly = y_data["hourly"]
    weekday = y_data["weekday"]
    order_type = y_data["order_type"]
    channel = y_data["channel"]
    hour_by_weekday = y_data["hour_by_weekday"]

    if hourly.empty and weekday.empty and order_type.empty:
        st.error("ยังไม่พบข้อมูลรายงานที่อ่านได้ในโฟลเดอร์ลูกค้า")
        st.stop()

    sales_total = float(hourly["sales"].sum()) if not hourly.empty else float(weekday["sales"].sum())
    orders_total = float(hourly["orders"].sum()) if not hourly.empty else float(weekday["orders"].sum())
    aov = sales_total / orders_total if orders_total else 0
    peak_hour = int(hourly.loc[hourly["sales"].idxmax(), "hour"]) if not hourly.empty else 0
    peak_day = str(weekday.loc[weekday["sales"].idxmax(), "dayOfWeek"]) if not weekday.empty else "-"

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Sales", f"฿{sales_total:,.0f}")
    m2.metric("Total Orders", f"{orders_total:,.0f}")
    m3.metric("AOV", f"฿{aov:,.0f}")
    m4.metric("Peak Time", f"{peak_hour:02d}:00 / {peak_day}")

    t1, t2, t3, t4 = st.tabs(["Executive Dashboard", "Customer Intelligence", "Real-time Marketing", "Operations"])

    with t1:
        st.subheader("มุมมองยอดขายตามช่วงเวลา")
        time_granularity = st.radio("เลือกระดับเวลา", ["รายชั่วโมง", "รายวัน", "รายเดือน"], horizontal=True)
        daily_ts = pd.DataFrame()
        monthly_ts = pd.DataFrame()
        if not channel.empty and {"time", "sales"}.issubset(set(channel.columns)):
            ts = channel.copy()
            ts["time"] = pd.to_datetime(ts["time"], errors="coerce")
            ts = ts.dropna(subset=["time"])
            if "channel" in ts.columns and (ts["channel"] == "TOTAL").any():
                ts = ts[ts["channel"] == "TOTAL"].copy()
            ts = ts.groupby("time", as_index=False)["sales"].sum()
            daily_ts = ts.sort_values("time")
            if not daily_ts.empty:
                monthly_ts = (
                    daily_ts.assign(month=daily_ts["time"].dt.to_period("M").astype(str))
                    .groupby("month", as_index=False)["sales"].sum()
                )
        if time_granularity == "รายชั่วโมง":
            if not hourly.empty:
                _chart(px.bar(hourly, x="hour", y="sales", title="ยอดขายตามชั่วโมง"))
            else:
                st.warning("ไม่พบข้อมูลรายชั่วโมง")
        elif time_granularity == "รายวัน":
            if not daily_ts.empty:
                _chart(px.line(daily_ts, x="time", y="sales", markers=True, title="ยอดขายรายวัน"))
            else:
                st.warning("ไม่พบข้อมูลรายวัน")
        else:
            if not monthly_ts.empty:
                _chart(px.bar(monthly_ts, x="month", y="sales", title="ยอดขายรายเดือน"))
            else:
                st.warning("ไม่พบข้อมูลรายเดือน")
        if not hourly.empty:
            top_h = hourly.sort_values("sales", ascending=False).head(1)["hour"].tolist()
            if top_h:
                st.caption(f"Insight: ชั่วโมงขายดีที่สุดคือ {int(top_h[0]):02d}:00")
        if not weekday.empty:
            _chart(px.bar(weekday, x="dayOfWeek", y="sales", title="ยอดขายตามวันในสัปดาห์"))

    with t2:
        if not order_type.empty:
            _chart(px.pie(order_type, values="sales", names="orderType", title="สัดส่วนยอดขายตามประเภทออเดอร์"))
        if not channel.empty:
            ch_sum = channel.groupby("channel", as_index=False)[["sales", "orders"]].sum()
            _chart(px.bar(ch_sum, x="channel", y="sales", title="ยอดขายตามช่องทาง"))
        st.info("หมายเหตุ: ไฟล์ชุดนี้ยังไม่มี customer-level ID จึงวิเคราะห์รายบุคคลได้บางส่วน")

    with t3:
        if not hourly.empty:
            weak_h = hourly.sort_values("sales").head(3)["hour"].tolist()
            strong_h = hourly.sort_values("sales", ascending=False).head(2)["hour"].tolist()
            st.success(f"ช่วงยอดต่ำที่ควรกระตุ้น: {', '.join(f'{int(h):02d}:00' for h in weak_h)}")
            st.success(f"ช่วงพีคที่ควรทำ upsell: {', '.join(f'{int(h):02d}:00' for h in strong_h)}")
        if not order_type.empty and "avgBasketSize" in order_type.columns:
            best_type = order_type.sort_values("avgBasketSize", ascending=False).iloc[0]["orderType"]
            st.info(f"ประเภทออเดอร์ที่มูลค่าต่อบิลสูงสุด: {best_type}")
        st.markdown("**Recommended Actions:**")
        st.write("- ยิงโปรช่วงบ่ายก่อนพีค (15:00-17:00) เพื่อดึงทราฟฟิกก่อนดินเนอร์")
        st.write("- ทำคอนเทนต์ 'ชุดคุ้ม + ท็อปปิ้งเพิ่ม' ในช่วงพีคเพื่อดัน AOV")
        st.write("- รีมาร์เก็ตลูกค้าที่เคยสั่งช่วงพีค ให้กลับมาในวันยอดอ่อน")

    with t4:
        if not hour_by_weekday.empty:
            heat = hour_by_weekday.pivot_table(index="weekday", columns="hour", values="sales", aggfunc="sum").fillna(0)
            _chart(px.imshow(heat, aspect="auto", title="Heatmap ยอดขาย (วัน x ชั่วโมง)"))
        st.caption("ไฟล์ชุดนี้เน้นยอดขายเชิงรวม ยังไม่มีข้อมูลพนักงานรายคน")

    st.divider()
    st.markdown("**Next step:** เพิ่มไฟล์ลูกค้ารายบุคคล/พนักงาน เพื่อเปิด AI retention + staff intelligence แบบเต็ม")


# ── Content Studio ──────────────────────────────────────────────────────────────

def render_content_studio_page(ai_mode: str, api_key: str, line_token: str = "", fb_token: str = "", fb_page_id: str = "", ig_business_id: str = "") -> None:
    _page_head("📣 Content Studio", "AI สร้างคอนเทนต์จากข้อมูลธุรกิจ → Google Drive → โพสต์ทุกแพลตฟอร์ม")

    if not CONTENT_STUDIO_AVAILABLE:
        st.error("ไม่พบ content_studio.py — กรุณาตรวจสอบไฟล์ในโฟลเดอร์โปรเจกต์")
        return

    # ── Flowchart ──────────────────────────────────────────────────────────────
    is_dark = _theme == "dark"
    fc_bg   = "#111827" if is_dark else "#FFFFFF"
    fc_bdr  = "rgba(255,255,255,0.08)" if is_dark else "rgba(0,0,0,0.08)"
    fc_txt  = "#E5E7EB" if is_dark else "#1F2937"
    fc_sub  = "#9CA3AF" if is_dark else "#6B7280"
    arrow   = "#F59E0B"

    st.markdown(f"""
<style>
@keyframes flowPulse {{
  0%,100% {{ opacity:0.5; transform:scaleX(1); }}
  50%      {{ opacity:1;   transform:scaleX(1.08); }}
}}
.cs-flow {{ display:flex; align-items:center; gap:0; overflow-x:auto; padding:1.2rem 0 0.5rem; }}
.cs-node {{
  background:{fc_bg}; border:1px solid {fc_bdr}; border-radius:14px;
  padding:14px 18px; min-width:130px; text-align:center; flex-shrink:0;
  transition:transform .18s,box-shadow .18s;
}}
.cs-node:hover {{ transform:translateY(-3px); box-shadow:0 8px 24px rgba(245,158,11,.18); }}
.cs-node-icon {{ font-size:1.6rem; line-height:1; margin-bottom:4px; }}
.cs-node-label {{ font-size:12.5px; font-weight:600; color:{fc_txt}; }}
.cs-node-sub   {{ font-size:10.5px; color:{fc_sub}; margin-top:2px; }}
.cs-arrow {{ color:{arrow}; font-size:1.3rem; padding:0 6px; flex-shrink:0;
             animation:flowPulse 2s ease-in-out infinite; }}
</style>
<div class="cs-flow">
  <div class="cs-node">
    <div class="cs-node-icon">📊</div>
    <div class="cs-node-label">Business Data</div>
    <div class="cs-node-sub">ยอดขาย / Segment</div>
  </div>
  <div class="cs-arrow">→</div>
  <div class="cs-node">
    <div class="cs-node-icon">🤖</div>
    <div class="cs-node-label">AI Generate</div>
    <div class="cs-node-sub">Text / ไอเดียภาพ</div>
  </div>
  <div class="cs-arrow">→</div>
  <div class="cs-node" style="border-color:#F59E0B40;background:{'#1C1B15' if is_dark else '#FFFBEB'};">
    <div class="cs-node-icon">📁</div>
    <div class="cs-node-label">Google Drive</div>
    <div class="cs-node-sub">Content Hub</div>
  </div>
  <div class="cs-arrow">→</div>
  <div class="cs-node">
    <div class="cs-node-icon">💚</div>
    <div class="cs-node-label">LINE OA</div>
    <div class="cs-node-sub">Text + Image</div>
  </div>
  <div class="cs-arrow" style="font-size:1rem;">+</div>
  <div class="cs-node">
    <div class="cs-node-icon">🔵</div>
    <div class="cs-node-label">Facebook</div>
    <div class="cs-node-sub">Post / Reel</div>
  </div>
  <div class="cs-arrow" style="font-size:1rem;">+</div>
  <div class="cs-node">
    <div class="cs-node-icon">🟣</div>
    <div class="cs-node-label">Instagram</div>
    <div class="cs-node-sub">Feed / Story</div>
  </div>
  <div class="cs-arrow" style="font-size:1rem;">+</div>
  <div class="cs-node">
    <div class="cs-node-icon">⬛</div>
    <div class="cs-node-label">TikTok</div>
    <div class="cs-node-sub">Short Video</div>
  </div>
  <div class="cs-arrow" style="font-size:1rem;">+</div>
  <div class="cs-node">
    <div class="cs-node-icon">🔴</div>
    <div class="cs-node-label">YouTube</div>
    <div class="cs-node-sub">Shorts / Video</div>
  </div>
</div>
""", unsafe_allow_html=True)

    st.divider()

    # ── Campaign setup ─────────────────────────────────────────────────────────
    col_left, col_right = st.columns([1, 1], gap="large")

    with col_left:
        st.subheader("🎯 ตั้งค่า Campaign")

        campaign_key = st.selectbox(
            "ประเภท Campaign",
            options=list(CAMPAIGN_TYPES.keys()),
            format_func=lambda k: CAMPAIGN_TYPES[k]["label"],
        )
        campaign_info = CAMPAIGN_TYPES[campaign_key]
        st.caption(campaign_info.get("goal", ""))

        tone_key = st.selectbox(
            "โทนเสียง",
            options=list(TONES.keys()),
            format_func=lambda k: f"{k.capitalize()} — {TONES[k]}",
        )

        st.markdown("**แพลตฟอร์มที่ต้องการ**")
        selected_platforms: list[str] = []
        pcols = st.columns(3)
        for i, (pid, pmeta) in enumerate(PLATFORMS.items()):
            with pcols[i % 3]:
                if st.checkbox(f"{pmeta['icon']} {pmeta['name']}", value=True, key=f"plat_{pid}"):
                    selected_platforms.append(pid)

    with col_right:
        st.subheader("📋 ข้อมูลธุรกิจ")

        biz_name = st.text_input("ชื่อร้าน / แบรนด์", value="ร้านของคุณ", placeholder="เช่น Café Bloom")
        hero_product = st.text_input("สินค้า / เมนู Hero", value="เมนูเด็ด", placeholder="เช่น ชาไทยเย็น, หมูกระทะ unlimited")
        discount_pct = st.number_input("ส่วนลด (%)", min_value=5, max_value=80, value=20, step=5)
        expiry_date = st.text_input("วันหมดอายุโปร", value="31 ธ.ค.", placeholder="เช่น 31 ธ.ค.")
        cta_text = st.text_input("CTA / ลิงก์", value="ทักแชทเพื่อรับสิทธิ์", placeholder="เช่น คลิก https://...")

        target_segment = st.selectbox(
            "Target Segment",
            ["Champions", "Loyal Customers", "At Risk", "Potential Loyalists", "Recent Customers", "ทุกกลุ่ม"],
        )

        if campaign_key in ("flash_sale", "winback"):
            days_inactive = st.slider("ลูกค้าหายไปกี่วัน", 7, 90, 30)
        else:
            days_inactive = 0

        if campaign_key == "flash_sale":
            urgency = st.slider("ความเร่งด่วน (ชั่วโมง)", 1, 72, 24)
            start_time = st.text_input("เวลาเริ่ม", value="17:00")
            end_time = st.text_input("เวลาจบ", value="20:00")
        else:
            urgency = 0
            start_time = "17:00"
            end_time = "20:00"

        st.markdown("**🖼️ รูปภาพประกอบ (ไม่บังคับ)**")
        uploaded_image = st.file_uploader(
            "อัปโหลดรูป",
            type=["jpg", "jpeg", "png"],
            help="ภาพจะแนบไปกับ Facebook + LINE OA + Instagram (feed)",
            key="cs_image_upload",
            label_visibility="collapsed",
        )
        if uploaded_image is not None:
            st.session_state["cs_image_bytes"] = uploaded_image.getvalue()
            st.session_state["cs_image_name"] = uploaded_image.name
            st.image(uploaded_image, caption="✅ ภาพพร้อมโพสต์", width=200)
        elif "cs_image_bytes" in st.session_state:
            if st.button("🗑️ ลบรูป", width="stretch", key="del_img"):
                del st.session_state["cs_image_bytes"]
                del st.session_state["cs_image_name"]
                st.rerun()

        st.markdown("**🎬 วิดีโอ (ไม่บังคับ)**")
        uploaded_video = st.file_uploader(
            "อัปโหลดวิดีโอ",
            type=["mp4", "mov"],
            help="วิดีโอจะใช้กับ Instagram Reels + YouTube + TikTok",
            key="cs_video_upload",
            label_visibility="collapsed",
        )
        if uploaded_video is not None:
            st.session_state["cs_video_bytes"] = uploaded_video.getvalue()
            st.session_state["cs_video_name"] = uploaded_video.name
            size_mb = len(st.session_state["cs_video_bytes"]) / 1024 / 1024
            st.success(f"✅ วิดีโอพร้อม ({size_mb:.1f} MB)")
        elif "cs_video_bytes" in st.session_state:
            if st.button("🗑️ ลบวิดีโอ", width="stretch", key="del_vid"):
                del st.session_state["cs_video_bytes"]
                del st.session_state["cs_video_name"]
                st.rerun()

    st.divider()

    # ── Generate ───────────────────────────────────────────────────────────────
    use_claude = ai_mode == "Claude API" and api_key.strip() and ANTHROPIC_AVAILABLE
    btn_label = "🤖 Generate with Claude AI" if use_claude else "⚡ Generate with Local AI"

    if st.button(btn_label, type="primary", width="stretch"):
        # Keys must match placeholders in content_studio.py templates
        _brand = biz_name or "ร้านของคุณ"
        _hero = hero_product or "เมนูเด็ด"
        context = {
            "brand_name": _brand,
            "brand_tag": _brand.replace(" ", "").replace("ร้าน", ""),
            "top_item": _hero,
            "discount": discount_pct,
            "expiry": expiry_date,
            "cta": cta_text,
            "days": days_inactive,
            "hours": "10:00-22:00",
            "start_time": start_time,
            "end_time": end_time,
            "countdown": urgency,
            # also keep old keys for compatibility
            "business_name": _brand,
            "hero_product": _hero,
            "target_segment": target_segment,
            "days_inactive": days_inactive,
            "urgency_hours": urgency,
        }
        with st.spinner("กำลังสร้างคอนเทนต์..."):
            package = get_content_package(
                campaign_type=campaign_key,
                context=context,
                tone=tone_key,
                api_key=api_key.strip() if use_claude else "",
            )
        st.session_state["cs_package"] = package
        st.session_state["cs_campaign"] = campaign_key
        st.session_state["cs_platforms"] = selected_platforms
        st.success("สร้างคอนเทนต์สำเร็จ! เลื่อนลงเพื่อดูและโพสต์")

    # ── Content display ────────────────────────────────────────────────────────
    if "cs_package" not in st.session_state:
        _notice_bg = "#1C1B15" if is_dark else "#FFFBEF"
        _notice_bd = "#F59E0B40"
        _notice_tx = "#D97706" if is_dark else "#92400E"
        st.markdown(
            f'<div style="background:{_notice_bg};border:1px solid {_notice_bd};border-radius:12px;'
            f'padding:1.2rem 1.5rem;margin-top:0.5rem;">'
            f'<p style="color:{_notice_tx};margin:0;font-size:0.9rem;">💡 กรอกข้อมูลด้านบนแล้วกด Generate เพื่อสร้างคอนเทนต์พร้อมโพสต์</p>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    package   = st.session_state["cs_package"]
    sel_plats = st.session_state.get("cs_platforms", list(PLATFORMS.keys()))

    st.divider()
    st.subheader("📝 คอนเทนต์ที่สร้างแล้ว")

    # tabs per platform
    visible = [p for p in sel_plats if p in package]
    if not visible:
        st.warning("ไม่พบคอนเทนต์สำหรับแพลตฟอร์มที่เลือก — ลองกด Generate ใหม่")
        return

    tab_labels = [f"{PLATFORMS[p]['icon']} {PLATFORMS[p]['name']}" for p in visible]
    tabs = st.tabs(tab_labels)

    for tab, pid in zip(tabs, visible):
        content = package.get(pid, "")
        # content is a plain string from get_content_package()
        full_text = content if isinstance(content, str) else ""
        pmeta   = PLATFORMS[pid]
        with tab:
            c_txt_col, c_act_col = st.columns([2, 1])
            with c_txt_col:
                edited = st.text_area(
                    f"คอนเทนต์ {pmeta['name']}",
                    value=full_text,
                    height=220,
                    key=f"cs_text_{pid}",
                )
                char_count = len(edited)
                max_chars  = pmeta.get("max_chars", 2200)
                bar_pct    = min(char_count / max_chars, 1.0)
                bar_color  = "#EF4444" if bar_pct > 0.9 else "#10B981"
                st.markdown(
                    f'<div style="height:4px;border-radius:2px;background:rgba(128,128,128,.15);">'
                    f'<div style="height:4px;border-radius:2px;width:{bar_pct*100:.0f}%;background:{bar_color};transition:width .3s;"></div>'
                    f'</div>'
                    f'<p style="font-size:11px;color:#9CA3AF;margin:3px 0 0;">{char_count:,} / {max_chars:,} ตัวอักษร</p>',
                    unsafe_allow_html=True,
                )

            with c_act_col:
                st.markdown(f"**Best Post Time**")
                best_hours = pmeta.get("best_hours", [])
                for h in best_hours:
                    st.markdown(f"🕐 `{h:02d}:00 น.`")

                routes = pmeta.get("routes", [])
                st.markdown(f"**Content Types**")
                for r in routes:
                    icons = {"text": "📝", "image": "🖼️", "video": "🎬", "carousel": "🎠"}
                    st.markdown(f"{icons.get(r, '•')} {r.capitalize()}")

                st.markdown("---")
                # Mock publish button
                col_save, col_post = st.columns(2)
                with col_save:
                    st.download_button(
                        "📁 Save",
                        data=edited.encode("utf-8"),
                        file_name=f"{pid}_content.txt",
                        mime="text/plain",
                        width="stretch",
                        key=f"dl_{pid}",
                    )
                with col_post:
                    if st.button(
                        f"🚀 Post",
                        width="stretch",
                        key=f"post_{pid}",
                        type="primary",
                    ):
                        _do_post(
                            pid, edited, line_token, fb_token, fb_page_id,
                            ig_business_id=ig_business_id,
                            image_bytes=st.session_state.get("cs_image_bytes"),
                            image_name=st.session_state.get("cs_image_name", "image.jpg"),
                            video_bytes=st.session_state.get("cs_video_bytes"),
                            video_name=st.session_state.get("cs_video_name", "video.mp4"),
                        )

                    # TikTok download helper (always shown for tiktok tab)
                    if pid == "tiktok" and st.session_state.get("cs_video_bytes"):
                        st.download_button(
                            "📥 Download วิดีโอ (สำหรับ TikTok)",
                            data=st.session_state["cs_video_bytes"],
                            file_name=st.session_state.get("cs_video_name", "video.mp4"),
                            mime="video/mp4",
                            key=f"dl_tiktok_{pid}",
                            width="stretch",
                        )
                        st.markdown("[🔗 เปิด TikTok เพื่ออัปโหลด](https://www.tiktok.com/upload)")

    # ── Post All ───────────────────────────────────────────────────────────────
    st.divider()
    pa_left, pa_right = st.columns([2, 1])
    with pa_left:
        st.markdown("**⚡ โพสต์ทุกแพลตฟอร์มในคลิกเดียว**")
        st.caption("ใช้คอนเทนต์ของแต่ละ tab (รวมที่แก้ไขแล้ว) — TikTok จะเตรียมไฟล์ให้ดาวน์โหลด")
    with pa_right:
        post_all_clicked = st.button("🚀 Post All", type="primary", width="stretch", key="post_all")

    if post_all_clicked:
        results = []
        progress = st.progress(0.0, text="เริ่มโพสต์...")
        for i, pid in enumerate(visible):
            pname = PLATFORM_THAI_NAMES.get(pid, pid)
            progress.progress(i / len(visible), text=f"กำลังโพสต์ {pname}...")
            content_i = st.session_state.get(f"cs_text_{pid}") or package.get(pid, "")
            ok, msg = _do_post(
                pid, content_i, line_token, fb_token, fb_page_id,
                ig_business_id=ig_business_id,
                image_bytes=st.session_state.get("cs_image_bytes"),
                image_name=st.session_state.get("cs_image_name", "image.jpg"),
                video_bytes=st.session_state.get("cs_video_bytes"),
                video_name=st.session_state.get("cs_video_name", "video.mp4"),
                quiet=True,
            )
            results.append((pname, ok, msg))
        progress.progress(1.0, text="เสร็จแล้ว!")

        n_ok = sum(1 for _, ok, _ in results if ok)
        if n_ok == len(results):
            st.success(f"🎉 โพสต์สำเร็จครบ {n_ok}/{len(results)} แพลตฟอร์ม")
        else:
            st.warning(f"สำเร็จ {n_ok}/{len(results)} แพลตฟอร์ม — ดูรายละเอียดด้านล่าง")
        for pname, ok, msg in results:
            st.markdown(f"{'✅' if ok else '❌'} **{pname}** — {msg}")

    # ── Posting schedule ───────────────────────────────────────────────────────
    st.divider()
    st.subheader("📅 ตารางโพสต์ที่แนะนำ")

    schedule_df = build_posting_schedule(visible, start_date=dt.date.today(), days=7)
    if schedule_df:
        sched_display = pd.DataFrame(schedule_df)
        sched_display["แพลตฟอร์ม"] = sched_display["platform_key"].map(
            lambda p: f"{PLATFORMS[p]['icon']} {PLATFORMS[p]['name']}" if p in PLATFORMS else p
        )
        sched_display["เวลาโพสต์"] = sched_display["date"].astype(str) + " " + sched_display["time"]
        sched_display["สถานะ"] = sched_display["status"]
        st.dataframe(sched_display[["แพลตฟอร์ม", "เวลาโพสต์", "สถานะ"]], width="stretch", hide_index=True)
    else:
        st.info("เลือกแพลตฟอร์มอย่างน้อย 1 แพลตฟอร์มเพื่อดูตารางโพสต์")

    # ── Google Drive export ────────────────────────────────────────────────────
    st.divider()
    st.subheader("📁 Export ไป Google Drive")

    all_content = "\n\n".join(
        f"=== {PLATFORMS[p]['name'].upper()} ===\n{package.get(p, '')}"
        for p in visible
    )
    filename = f"content_package_{dt.datetime.now().strftime('%Y%m%d_%H%M')}.txt"

    drive_col, dl_col = st.columns([1, 1])
    with drive_col:
        if GDRIVE_AVAILABLE:
            if needs_auth():
                st.warning("ยังไม่ได้ authorize Google Drive")
                if st.button("🔐 Authorize Google Drive", width="stretch"):
                    with st.spinner("กำลังเปิด browser..."):
                        run_first_time_auth()
                    st.success("Authorized แล้ว! กด Upload ได้เลย")
                    st.rerun()
            else:
                if st.button("☁️ Upload ไป Google Drive", type="primary", width="stretch"):
                    with st.spinner("กำลัง upload..."):
                        link = upload_text(all_content, filename, GDRIVE_FOLDER_ID)
                    if link:
                        st.success("Upload สำเร็จ!")
                        st.markdown(f"[📄 เปิดไฟล์ใน Drive]({link})")
                        st.session_state["last_drive_link"] = link
                    else:
                        st.error("Upload ไม่สำเร็จ")
                if "last_drive_link" in st.session_state:
                    st.markdown(f"[🔗 ไฟล์ล่าสุด]({st.session_state['last_drive_link']})")
        else:
            st.warning("ไม่พบ google_drive.py")

    with dl_col:
        st.download_button(
            label="💾 Download ไฟล์",
            data=all_content.encode("utf-8"),
            file_name=filename,
            mime="text/plain",
            width="stretch",
        )

    # ── Post history ───────────────────────────────────────────────────────────
    history = st.session_state.get("post_history", [])
    if history:
        st.divider()
        st.subheader("🕐 ประวัติการโพสต์ (เซสชันนี้)")
        st.dataframe(pd.DataFrame(reversed(history)), width="stretch", hide_index=True)
        if st.button("🗑️ ล้างประวัติ", key="clear_history"):
            st.session_state["post_history"] = []
            st.rerun()


# ── AI provider helpers ──────────────────────────────────────────────────────────

def _resolve_ai(ai_mode: str, api_key: str) -> tuple[str, str, str]:
    """Return (key, provider, label) for the selected AI mode.

    key is "" whenever the mode/credentials aren't usable, which makes every
    caller fall back to local templates automatically.
    """
    key = (api_key or "").strip()
    if ai_mode == "Gemini API" and key:
        return key, "gemini", "✨ Gemini"
    if ai_mode == "Claude API" and key and ANTHROPIC_AVAILABLE:
        return key, "claude", "🤖 Claude"
    return "", "local", "⚡ Local AI"


def _mandala_badge() -> None:
    """Show whether the Mandala brand context is wired in, with a refresh control."""
    try:
        import mandala_client
        info = mandala_client.status()
    except Exception:  # noqa: BLE001
        return
    if info.get("has_context"):
        st.caption(
            f"🔗 ใช้บริบทแบรนด์จาก Mandala AI ({info['context_chars']:,} ตัวอักษร"
            f" · {info['runs']} รอบที่ผลิตไว้)"
        )
    elif info.get("found"):
        st.caption("🔗 เจอ mandala-bot แต่ยังไม่มี context.txt")
    else:
        return

    # ดึงข้อมูลเพจ FB ล่าสุดเข้ามาอัปเดตบริบทแบรนด์ โดยไม่ต้องเปิด terminal mandala-bot แยก
    try:
        import mandala_refresh
    except Exception:  # noqa: BLE001
        return
    if st.button(
        "🔄 ดึงข้อมูลเพจ FB ล่าสุด",
        key="mandala_refresh_fb",
        help="รัน fb_insights ของ mandala-bot แล้วอัปเดตบริบทแบรนด์จากโพสต์+engagement จริง",
    ):
        with st.spinner("กำลังดึงข้อมูลเพจจาก Facebook..."):
            res = mandala_refresh.refresh_fb_insights()
        if res.get("ok"):
            st.success("อัปเดตบริบทแบรนด์จากเพจแล้ว")
            st.cache_data.clear()
            st.rerun()
        else:
            st.error("ดึงข้อมูลเพจไม่สำเร็จ (token FB อาจหมดอายุ — ต่อ token ใหม่ใน mandala-bot/.env)")
            with st.expander("รายละเอียด"):
                st.code((res.get("stderr") or res.get("stdout") or "")[-1500:])


@st.cache_data(ttl=600, show_spinner=False)
def _scene_scores() -> dict:
    """How well each scene angle fits this brand, scored off Mandala's own material.

    Reading the context files costs a disk hit per rerun and the answer only
    changes when Mandala produces a new run, so it is cached. Returns an empty
    dict when there is nothing to score against — callers then show no stars
    rather than an invented number.
    """
    if not SCENES_AVAILABLE:
        return {}
    try:
        import mandala_client
        text = mandala_client.build_context_block(include_samples=4, max_chars=20000)
    except Exception:  # noqa: BLE001
        return {}
    if not text:
        return {}
    try:
        return scene_presets.score_scenes(text)
    except Exception:  # noqa: BLE001
        return {}


# ── Approval queue (reads back from Google Drive) ────────────────────────────────

# How many files to draw per folder before offering "show more".
QUEUE_PAGE_SIZE = 15

# Listing the queue costs one Drive round trip per folder — measured at 6.5s for
# eight folders. Streamlit reruns the whole script on every click, so without a
# cache each approve, each "show more", each checkbox pays that again. The TTL
# keeps it fresh enough for a review queue; "โหลดใหม่" clears it outright.
QUEUE_CACHE_TTL = 60


@st.cache_data(ttl=QUEUE_CACHE_TTL, show_spinner=False)
def _cached_child_folders(root_id: str) -> dict:
    return list_child_folders(root_id)


@st.cache_data(ttl=QUEUE_CACHE_TTL, show_spinner=False)
def _cached_files(folder_id: str, oldest_first: bool) -> list[dict]:
    return list_files_in_folder(folder_id, oldest_first=oldest_first)


def _clear_queue_cache() -> None:
    _cached_child_folders.clear()
    _cached_files.clear()

# Folder name fragment → platform key, so a file's location decides where it posts.
_FOLDER_PLATFORM_HINTS = [
    (("facebook", "fb"), "facebook"),
    (("instagram", "instragram", "ig"), "instagram"),
    (("tiktok", "tik tok"), "tiktok"),
    (("youtube", "yt"), "youtube"),
    (("line",), "line_oa"),
]


def _platform_from_folder(name: str) -> str:
    low = (name or "").lower()
    for fragments, key in _FOLDER_PLATFORM_HINTS:
        if any(f in low for f in fragments):
            return key
    return ""


def _queue_caption_for(file: dict) -> str:
    """Text files in the queue are captions — read them for preview/posting."""
    if not (file.get("mimeType") or "").startswith("text/"):
        return ""
    data = download_file(file["id"])
    if not data:
        return ""
    try:
        return data.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def _render_flow_paste_links() -> None:
    """วางลิงก์ที่บุ๊กมาร์กเล็ตคัดลอกมา แล้วให้ Python โหลดไฟล์ลง Drive

    ไฟล์จริงของ Flow อยู่คนละโดเมนกับหน้าเว็บ เบราว์เซอร์จึงไม่ยอมให้สคริปต์ในหน้า
    โหลดมาเซฟเอง แต่ลิงก์ที่ CDN เซ็นมาใช้ได้โดยไม่ต้องมีคุกกี้ ฝั่งนี้จึงโหลดได้ตรง ๆ
    """
    st.markdown("**📥 วางลิงก์จาก Flow**")
    st.caption("กดบุ๊กมาร์กในหน้า Flow → กด “คัดลอกลิงก์ทั้งหมด” → วางที่นี่ → กดโหลด "
               "· ไฟล์จะลงโฟลเดอร์ที่ watcher เฝ้าอยู่ แล้วถูกจัดเข้าโฟลเดอร์แพลตฟอร์มเอง")

    text = st.text_area("ลิงก์ (บรรทัดละอัน)", height=110, key="flow_paste_links",
                        placeholder="https://flow-content.google/video/…")
    try:
        import flow_fetch
    except Exception as e:  # noqa: BLE001
        st.caption(f"⚠️ โหลดโมดูลไม่ได้: {e}")
        return

    urls = flow_fetch.parse_urls(text)
    if text and not urls:
        st.caption("ยังไม่เจอลิงก์ในข้อความที่วางมา")
    if urls:
        st.caption(f"เจอ {len(urls)} ลิงก์ (ตัดซ้ำแล้ว)")

    # ขึ้น Drive ตรงเป็นค่าเริ่มต้น — ไฟล์วิ่งจาก CDN เข้าหน่วยความจำแล้วขึ้นคลาวด์เลย
    # ไม่เหลืออะไรในเครื่อง และไม่ต้องรอ Drive for Desktop ซิงก์
    to_drive = st.radio(
        "ปลายทาง", ["☁️ ขึ้น Google Drive ตรง (ไม่ลงเครื่อง)", "💾 ลงเครื่องก่อน"],
        horizontal=True, key="flow_paste_dest", label_visibility="collapsed",
    ).startswith("☁️")

    if st.button(f"⬇️ โหลด {len(urls)} ไฟล์", disabled=not urls,
                 width="stretch", key="flow_paste_go"):
        prog = st.progress(0.0, text="กำลังเริ่ม…")
        track = lambda i, n, u: prog.progress((i - 1) / n, text=f"ไฟล์ {i}/{n}")  # noqa: E731
        if to_drive:
            results = flow_fetch.fetch_all_to_drive(urls, QUEUE_ROOT_FOLDER_ID,
                                                    on_progress=track)
        else:
            results = flow_fetch.fetch_all(urls, on_progress=track)
        prog.progress(1.0, text="เสร็จแล้ว")
        ok = [r for r in results if r.ok]
        (st.success if len(ok) == len(results) else st.warning)(
            f"โหลดสำเร็จ {len(ok)}/{len(results)} ไฟล์")
        for r in results:
            if r.ok:
                where = f" → {r.folder}" if r.folder else ""
                st.markdown(f"✅ **{r.path.name}** — {r.bytes / 1048576:.1f} MB{where}")
            else:
                st.markdown(f"❌ {r.url[:60]}… — {r.error}")
        if ok:
            _clear_queue_cache()   # ให้ไฟล์ใหม่โผล่ในคิวทันที


def _render_scene_score(filename: str) -> None:
    """What this file was shot for, and how well that angle fits the brand.

    Flow names each download after the prompt behind it, so the scene is usually
    recoverable from the filename. Says nothing at all when the scene cannot be
    read or there is no Mandala context to score against — an invented number on
    a file you are about to approve is worse than no number.
    """
    if not SCENES_AVAILABLE:
        return
    key = scene_presets.match_scene(filename)
    if not key:
        return
    goal = scene_presets.goal_for(key)
    score = _scene_scores().get(key, 0)
    stars = f"{'★' * score}{'·' * (5 - score)} " if score else ""
    st.caption(f"{stars}{scene_presets.label_for(key)} — {goal}")
    if score:
        st.caption("ดาวคือความเข้ากับแบรนด์จากบริบทใน Mandala AI "
                   "ไม่ใช่การทำนายยอด engagement")


def _brand_context_for_review() -> str:
    """The brand material the reviewer scores against."""
    try:
        import mandala_client
        block = mandala_client.build_context_block()
        if block:
            return block
    except Exception:  # noqa: BLE001 — mandala-bot is optional
        pass
    if COPILOT_AVAILABLE:
        try:
            return content_copilot.load_brand_context()
        except Exception:  # noqa: BLE001
            return ""
    return ""


def _run_ai_review(file: dict, platform: str, key: str, provider: str) -> None:
    """Download the file and have the model look at it. Result cached per file id."""
    fid = file["id"]
    data = st.session_state.get(f"q_data_{fid}") or download_file(fid)
    if not data:
        st.session_state[f"q_rev_err_{fid}"] = "โหลดไฟล์จาก Drive ไม่สำเร็จ"
        return
    # Keep the bytes: approving posts the same file, so this saves a second
    # download of something already in memory.
    st.session_state[f"q_data_{fid}"] = data
    review, err = queue_review.review_file(
        file["name"], file.get("mimeType", ""), data,
        brand_context=_brand_context_for_review(),
        api_key=key, provider=provider,
        platform=PLATFORM_THAI_NAMES.get(platform, ""),
    )
    st.session_state[f"q_rev_{fid}"] = review
    st.session_state[f"q_rev_err_{fid}"] = err


def _render_ai_review(file: dict, platform: str) -> None:
    """AI's read of the actual file — offered, not run automatically.

    Every review costs a download plus a model call, and a queue page lists up
    to 100 files. Running them all on load would spend real money answering a
    question nobody asked yet, so it happens on the button.
    """
    if not QUEUE_REVIEW_AVAILABLE:
        return
    fid = file["id"]
    mime = file.get("mimeType", "")
    # Resolved, not raw: _resolve_ai blanks the key whenever the mode cannot
    # actually run (Claude selected without the SDK installed, say), and asking
    # can_review with a key the app will not use would promise a review that
    # then fails.
    key, provider, _lbl = _resolve_ai(ai_mode := _s(K_AI, "Local Smart"),
                                      _resolve_api_key(ai_mode))

    review = st.session_state.get(f"q_rev_{fid}")
    err = st.session_state.get(f"q_rev_err_{fid}")
    ok, why = queue_review.can_review(mime, key, provider)

    if review is None and not err:
        if not ok:
            st.caption(f"🔍 ให้ AI ดูไฟล์จริง — {why}")
            return
        if st.button("🔍 ให้ AI ดูไฟล์จริงแล้วให้คะแนน", key=f"q_rev_go_{fid}",
                     width="stretch"):
            with st.spinner("กำลังให้ AI ดูไฟล์..."):
                _run_ai_review(file, platform, key, provider)
            st.rerun()
        return

    if err:
        st.warning(f"ตรวจไม่สำเร็จ: {err}")
    if review:
        label, tone = queue_review.VERDICT_THAI.get(review.verdict,
                                                    ("🛠️ ควรแก้ก่อน", "on"))
        chips = [(label, tone)]
        if review.fit:
            chips.append((f"{'★' * review.fit}{'·' * (5 - review.fit)} เข้ากับแบรนด์", "on"))
        if review.scene:
            chips.append((f"ฉาก: {review.scene}", ""))
        _chips(chips)

        if review.seen:
            st.markdown(f"**AI เห็นอะไร:** {review.seen}")
        if review.risk:
            st.warning(f"⚠️ {review.risk}")
        if review.strengths or review.fixes:
            g1, g2 = st.columns(2)
            with g1:
                if review.strengths:
                    st.markdown("**ข้อดี**\n" +
                                "\n".join(f"- {s}" for s in review.strengths))
            with g2:
                if review.fixes:
                    st.markdown("**ควรแก้**\n" +
                                "\n".join(f"- {s}" for s in review.fixes))
        st.caption("คะแนนนี้คือความเข้ากับแบรนด์ตามบริบทใน Mandala AI "
                   "ไม่ใช่การทำนายยอด engagement")

    if st.button("🔄 ตรวจใหม่", key=f"q_rev_again_{fid}"):
        st.session_state.pop(f"q_rev_{fid}", None)
        st.session_state.pop(f"q_rev_err_{fid}", None)
        st.rerun()


QUEUE_BATCH_CAP = 10


def _render_batch_review(files: list[dict], folder_name: str, platform: str) -> None:
    """Review a whole folder page in one go, with the cost stated up front.

    Capped and counted rather than "review everything": each file is a download
    plus a model call, and a folder can hold a hundred of them. Whatever the cap
    leaves out is said out loud — a batch that silently stops at ten reads as
    "all done" when it is not.
    """
    if not QUEUE_REVIEW_AVAILABLE or not files:
        return
    key, provider, _lbl = _resolve_ai(ai_mode := _s(K_AI, "Local Smart"),
                                      _resolve_api_key(ai_mode))
    todo = [f for f in files
            if st.session_state.get(f"q_rev_{f['id']}") is None
            and not st.session_state.get(f"q_rev_err_{f['id']}")
            and queue_review.can_review(f.get("mimeType", ""), key, provider)[0]]
    if not todo:
        return

    batch = todo[:QUEUE_BATCH_CAP]
    left = len(todo) - len(batch)
    label = f"🔍 ให้ AI ตรวจ {len(batch)} ไฟล์ในโฟลเดอร์นี้"
    if left:
        label += f" (เหลืออีก {left} กดซ้ำได้)"
    if not st.button(label, key=f"q_batch_{folder_name}", width="stretch"):
        return

    bar = st.progress(0.0, text="กำลังตรวจ...")
    for i, f in enumerate(batch, 1):
        bar.progress(i / len(batch), text=f"กำลังตรวจ {f['name']} ({i}/{len(batch)})")
        _run_ai_review(f, platform, key, provider)
    bar.empty()
    st.rerun()


def _render_move_to_platform(file: dict, all_folders: dict, current: str = "") -> None:
    """Let the reviewer say where this clip is going.

    A clip that arrives without a platform in its name is not a TikTok clip we
    failed to recognise — it has no platform yet. The choice belongs here, where
    someone is looking at the clip and deciding, not to a guess made from a
    filename at download time. Offered for every file, since a guessed platform
    can be wrong too and one clip often suits more than one place.
    """
    fid = file["id"]
    targets = sorted(n for n in all_folders
                     if n.upper() not in {"POSTED", "REJECTED"} and n != current)
    if not targets:
        return
    c1, c2 = st.columns([3, 1])
    with c1:
        dest = st.selectbox("ย้ายไปโฟลเดอร์", options=targets,
                            key=f"q_dest_{fid}", label_visibility="collapsed")
    with c2:
        if st.button("📁 ย้าย", key=f"q_move_{fid}", width="stretch"):
            if move_file(fid, all_folders[dest]):
                _clear_queue_cache()
                st.toast(f"ย้ายไป {dest} แล้ว", icon="📁")
                st.rerun()
            else:
                st.error("ย้ายไม่สำเร็จ")



def _render_sequence_breakdown(file: dict) -> None:
    """Parse and display shot sequence (Hook -> Decision -> CTA) and source prompt."""
    name = file.get("name", "")
    desc = file.get("description", "")
    
    # Check if there is an associated prompt or storyboard info in memory / drive
    import re
    # Try to find corresponding task or text prompt
    fid = file.get("id")
    prompt_text = ""
    try:
        import flow_queue
        # If filename has task id or timestamp
        m = re.search(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', name)
        if m:
            task = flow_queue.get_request_status(m.group(1))
            if task and task.get("prompt"):
                prompt_text = task.get("prompt")
    except Exception:
        pass

    with st.expander("🎬 ดู Sequence & Prompt ที่ใช้สร้างคลิปนี้", expanded=False):
        if prompt_text:
            # Parse beats
            hook_m = re.search(r'\[HOOK[^\]]*\](.*?)(?=\[DECISION|\[CTA|\[|$)', prompt_text, re.DOTALL | re.I)
            dec_m = re.search(r'\[DECISION[^\]]*\](.*?)(?=\[CTA|\[|$)', prompt_text, re.DOTALL | re.I)
            cta_m = re.search(r'\[CTA[^\]]*\](.*?)(?=\[STORYBOARD|\[PHYSICS|\[|$)', prompt_text, re.DOTALL | re.I)
            
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("🎯 **Shot 1: Hook (0-3s)**")
                if hook_m:
                    st.caption(hook_m.group(1).strip()[:180] + "...")
                else:
                    st.caption("เปิดเรื่องสะดุดตา หยุดนิ้วคนดู")
            with c2:
                st.markdown("✨ **Shot 2: Decision (3-7s)**")
                if dec_m:
                    st.caption(dec_m.group(1).strip()[:180] + "...")
                else:
                    st.caption("โชว์สินค้าจริง สรรพคุณ และวิธีใช้")
            with c3:
                st.markdown("🚀 **Shot 3: CTA (7-10s)**")
                if cta_m:
                    st.caption(cta_m.group(1).strip()[:180] + "...")
                else:
                    st.caption("ปิดจบ ชวนทักแชท / สั่งซื้อ")
            
            st.divider()
            st.caption("📋 **Master Prompt ต้นฉบับ:**")
            st.code(prompt_text, language=None)
        else:
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("🎯 **Shot 1 (0:00 - 0:03)**")
                st.caption("🪝 **Hook:** หยุดนิ้วคนดูด้วยปัญหาสิว/หน้ามัน")
            with c2:
                st.markdown("✨ **Shot 2 (0:03 - 0:07)**")
                st.caption("🧼 **Decision:** โชว์สบู่ก้อน LEMED ตีฟองนุ่ม ล้างสะอาดไม่แห้งตึง")
            with c3:
                st.markdown("🚀 **Shot 3 (0:07 - 0:10)**")
                st.caption("🛒 **CTA:** ยิ้มมั่นใจ โชว์สบู่ ชวนทักแชทรับโปรโมชั่น")


def _render_queue_file(folder_name: str, platform: str, file: dict,
                       line_token: str, fb_token: str, fb_page_id: str,
                       ig_business_id: str, all_folders: dict | None = None,
                       index: int = 1, folder_files: list | None = None) -> None:
    """One queued item: preview, then approve-and-post or reject."""
    mime = file.get("mimeType", "")
    fid = file["id"]
    size_mb = int(file.get("size") or 0) / 1024 / 1024

    with st.container(border=True):
        filename = (file.get("name") or "").lower()
        is_video = mime.startswith("video/") or filename.endswith((".mp4", ".mov", ".avi", ".webm", ".mkv"))
        is_image = mime.startswith("image/") or filename.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"))
        
        # สร้าง Serial Number เฉพาะของแต่ละรายการ
        prefix = "VDO" if is_video else ("IMG" if is_image else "POST")
        short_id = fid[-6:].upper()
        date_str = file.get('createdTime', '')[:10].replace('-', '')
        serial_code = f"#{index:02d} | LMD-{prefix}-{short_id}"
        
        # Header Badge ด้านบนสุดของการ์ด
        h_col1, h_col2 = st.columns([2, 1])
        with h_col1:
            badge_icon = "🎬" if is_video else ("🖼️" if is_image else "📝")
            st.markdown(f"### {badge_icon} `{serial_code}`")
        with h_col2:
            st.caption(f"📁 **{folder_name}** ({size_mb:.1f} MB)")

        st.divider()
        #
        # คนที่มากดอนุมัติตัดสินใจจากตัวคลิป ตัวภาพ หรือตัวข้อความ ไม่ใช่จากชื่อไฟล์
        # อย่าง flow_df3978e5.mp4 ซึ่งไม่บอกอะไรเลย ของเดิมเอาชื่อไฟล์ขึ้นก่อนแล้วซ่อน
        # ของจริงไว้หลังปุ่ม "กดโหลดเมื่อต้องการดู" — กลับหัวกับสิ่งที่หน้านี้มีไว้ทำ
        media_bytes = None
        caption = ""

        filename = (file.get("name") or "").lower()
        is_video = mime.startswith("video/") or filename.endswith((".mp4", ".mov", ".avi", ".webm", ".mkv"))
        is_image = mime.startswith("image/") or filename.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"))

        if is_image and not is_video:
            thumb = file.get("thumbnailLink")
            if thumb:
                try:
                    st.image(thumb.replace("=s220", "=s800"), width="stretch")
                except Exception:
                    pass
            if st.button("🔍 ดูรูปเต็ม", key=f"q_prev_{fid}", width="stretch"):
                st.session_state[f"q_data_{fid}"] = download_file(fid)
            media_bytes = st.session_state.get(f"q_data_{fid}")
            if media_bytes is not None:
                if len(media_bytes) < 100:
                    st.warning("⚠️ ไฟล์นี้ใน Google Drive มีขนาด 0 KB (ว่างเปล่า)")
                else:
                    try:
                        st.image(media_bytes, width="stretch")
                    except Exception:
                        st.info("💡 ไม่สามารถเปิดแสดงรูปภาพได้โดยตรง (กดดาวน์โหลดไฟล์ด้านล่างได้ครับ)")
        elif is_video:
            # Bypass Google third-party cookie restrictions entirely by streaming video directly from local server
            if f"play_vdo_{fid}" not in st.session_state:
                st.session_state[f"play_vdo_{fid}"] = False
            
            if not st.session_state[f"play_vdo_{fid}"]:
                if st.button("🎬 กดโหลดวิดีโอเพื่อเล่น (เลี่ยงปัญหาคุกกี้ / หน้าจอค้าง)", key=f"btn_play_{fid}", width="stretch"):
                    with st.spinner("กำลังโหลดข้อมูลวิดีโอ... (ใช้เวลาประมาณ 1-3 วินาที)"):
                        media_bytes = download_file(fid)
                        if media_bytes:
                            st.session_state[f"q_data_{fid}"] = media_bytes
                            st.session_state[f"play_vdo_{fid}"] = True
                            st.rerun()
                        else:
                            st.error("ไม่สามารถดึงไฟล์วิดีโอจาก Google Drive ได้")
            else:
                media_bytes = st.session_state.get(f"q_data_{fid}")
                if media_bytes is not None:
                    if len(media_bytes) < 1000:
                        st.warning("⚠️ ไฟล์วิดีโอนี้ใน Google Drive มีขนาด 0 KB (ว่างเปล่า)")
                    else:
                        try:
                            import tempfile, os
                            tmp_path = os.path.join(tempfile.gettempdir(), f"st_video_cache_{fid}.mp4")
                            if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) != len(media_bytes):
                                with open(tmp_path, "wb") as f:
                                    f.write(media_bytes)
                            st.video(tmp_path, format="video/mp4")
                        except Exception as e:
                            st.error(f"ไม่สามารถเล่นวิดีโอได้: {e}")
                
                if st.button("⏸️ ซ่อนเครื่องเล่นวิดีโอ", key=f"btn_hide_{fid}", width="stretch"):
                    st.session_state[f"play_vdo_{fid}"] = False
                    st.rerun()
        # เผยแพร่แคปชั่นดึงจากไฟล์
        caption = _queue_caption_for(file)
        
        # ค้นหาไฟล์แคปชั่นที่มีชื่อตรงกันเพื่อแสดงร่วมกับวิดีโอ/ภาพ
        if not caption and (is_video or is_image) and folder_files:
            import os
            current_name = file.get("name", "")
            base_name, _ = os.path.splitext(current_name)
            for f in folder_files:
                f_name = f.get("name", "")
                f_base, f_ext = os.path.splitext(f_name)
                if f_base == base_name and (f_ext.lower() == ".txt" or (f.get("mimeType") or "").startswith("text/")):
                    caption = _queue_caption_for(f)
                    break

        # แสดงให้กรอก/แก้ไขข้อความที่จะโพสต์สำหรับทุกประเภทไฟล์
        text_to_post = st.text_area("✍️ แก้ไขข้อความที่จะโพสต์", value=caption, height=140, key=f"q_cap_{fid}")

        # แสดง Sequence แยกแต่ละช็อตของคลิปและ Prompt
        if is_video or mime.startswith("video/"):
            _render_sequence_breakdown(file)

        _render_ai_review(file, platform)

        top, act = st.columns([3, 1])
        with top:
            _render_scene_score(file["name"])
            st.caption(f"{PLATFORM_THAI_NAMES.get(platform, folder_name)} · "
                       f"{mime.split('/')[-1]} · {size_mb:.1f} MB · "
                       f"{file.get('createdTime', '')[:16].replace('T', ' ')} · "
                       f"{file['name']}")
        with act:
            if file.get("webViewLink"):
                st.markdown(f"[🔗 เปิดใน Drive]({file['webViewLink']})")

        # เลือกปลายทางย้ายโฟลเดอร์ใน Google Drive
        if all_folders:
            _render_move_to_platform(file, all_folders, folder_name)

        # ── เลือกแพลตฟอร์มที่จะโพสต์จริง ──────────────────────────────────────────
        platform_keys = ["facebook", "instagram", "line_oa", "youtube", "tiktok"]
        default_platform_idx = platform_keys.index(platform) if platform in platform_keys else 0
        
        selected_post_platform = st.selectbox(
            "📢 เลือกแพลตฟอร์มที่จะส่งโพสต์",
            options=platform_keys,
            index=default_platform_idx,
            format_func=lambda k: PLATFORM_THAI_NAMES.get(k, k),
            key=f"q_post_plat_{fid}"
        )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ อนุมัติ + โพสต์", key=f"q_ok_{fid}",
                         type="primary", width="stretch"):
                data = media_bytes or (download_file(fid)
                                       if mime.startswith(("image/", "video/")) else None)
                ok, msg = _do_post(
                    selected_post_platform, text_to_post or file["name"],
                    line_token, fb_token, fb_page_id,
                    ig_business_id=ig_business_id,
                    image_bytes=data if mime.startswith("image/") else None,
                    image_name=file["name"],
                    video_bytes=data if mime.startswith("video/") else None,
                    video_name=file["name"],
                )
                if ok:
                    dest = ensure_subfolder(QUEUE_ROOT_FOLDER_ID, "POSTED")
                    if dest and move_file(fid, dest):
                        st.success(f"{msg} — ย้ายไฟล์ไปโฟลเดอร์ POSTED แล้ว")
                    else:
                        st.warning(f"{msg} — แต่ย้ายไฟล์ไม่สำเร็จ")
                    # The listing just changed; a stale cache would keep showing
                    # a file that is no longer in the queue.
                    _clear_queue_cache()
                    st.rerun()
                else:
                    st.error(msg)
        with c2:
            if st.button("❌ ไม่อนุมัติ", key=f"q_no_{fid}", width="stretch"):
                dest = ensure_subfolder(QUEUE_ROOT_FOLDER_ID, "REJECTED")
                if dest and move_file(fid, dest):
                    st.info("ย้ายไปโฟลเดอร์ REJECTED แล้ว")
                    _clear_queue_cache()
                    st.rerun()
                else:
                    st.error("ย้ายไฟล์ไม่สำเร็จ")


def _render_flow_sync(authed: bool = True) -> None:
    """Pull freshly downloaded Google Flow exports into the right Drive folders."""
    if not FLOW_SYNC_AVAILABLE:
        return

    with st.expander("⬇️ ซิงก์ไฟล์จาก Google Flow", expanded=not authed):
        st.caption(
            "Flow ไม่มี API ให้ดึงไฟล์ออกโดยตรง — ให้กดดาวน์โหลดจาก Flow ตามปกติ "
            "แล้วระบบจะหยิบไฟล์ใหม่ในโฟลเดอร์นี้ไปเข้า Drive ให้เอง"
        )
        st.link_button("🎬 ไปดาวน์โหลดจาก Google Flow", FLOW_PROJECT_URL,
                       width="stretch")

        local_root = flow_sync.default_local_root()
        if local_root:
            st.success(f"⚡ โหมดย้ายไฟล์ในเครื่อง — `{local_root}` "
                       "(เร็วกว่า ไม่กินโควตา API และ Drive ซิงก์ขึ้นคลาวด์ให้เอง)")
        else:
            st.caption("โหมดอัปโหลดผ่าน Drive API — ถ้าติดตั้ง Google Drive for Desktop "
                       "ระบบจะเปลี่ยนไปย้ายไฟล์ในเครื่องให้อัตโนมัติ (เร็วกว่ามาก)")
        default_dir = str(flow_sync.default_watch_dir())
        watch = st.text_input("โฟลเดอร์ที่ไฟล์ดาวน์โหลดลง", value=default_dir,
                              key="flow_watch_dir")
        c1, c2 = st.columns(2)
        with c1:
            hours = st.selectbox(
                "ดูเฉพาะไฟล์ใหม่ภายใน", options=[6, 24, 72, 0], index=1,
                format_func=lambda h: "ทั้งหมด" if h == 0 else f"{h} ชั่วโมง",
                key="flow_watch_hours",
            )
        with c2:
            st.caption("ไฟล์ที่ซิงก์แล้วจะถูกย้ายไปโฟลเดอร์ย่อย `_synced` "
                       "เพื่อไม่ให้อัปซ้ำ")

        pending = flow_sync.find_new_files(Path(watch), hours) if watch else []
        overrides: dict[str, str] = {}
        if pending:
            st.info(f"เจอไฟล์ใหม่ {len(pending)} ไฟล์ — เลือกปลายทางของแต่ละไฟล์")
            st.caption("Flow ตั้งชื่อไฟล์โดยไม่บอกแพลตฟอร์ม จึงต้องเลือกเอง "
                       "(หรือตั้งชื่อไฟล์ให้มี `ig` / `fb` / `tiktok` / `yt` แล้วเลือก อัตโนมัติ)")
            dest_options = ["auto", "facebook", "instagram", "tiktok", "youtube",
                            "line_oa", "skip"]
            for p in pending[:20]:
                kind = flow_sync.classify(p)
                guessed = flow_sync.guess_platform(p.name)
                fc, dc = st.columns([2, 1])
                with fc:
                    st.markdown(f"{'🖼️' if kind == 'image' else '🎬'} `{p.name[:52]}`")
                with dc:
                    overrides[p.name] = st.selectbox(
                        "ปลายทาง",
                        options=dest_options,
                        index=dest_options.index(guessed) if guessed in dest_options else 0,
                        format_func=lambda v: {
                            "auto": "🔎 อัตโนมัติ",
                            "skip": "⏭️ ข้ามไฟล์นี้",
                        }.get(v, PLATFORM_THAI_NAMES.get(v, v)),
                        key=f"flow_dest_{p.name}",
                        label_visibility="collapsed",
                    )
            # "auto" means "no override" as far as the sync layer is concerned.
            overrides = {k: ("" if v == "auto" else v) for k, v in overrides.items()}
        else:
            st.caption("ยังไม่เจอไฟล์ใหม่ในโฟลเดอร์นี้")

        # Moving into the Drive-for-Desktop mirror needs no API access at all.
        can_sync = authed or local_root is not None
        if not can_sync:
            st.caption("🔐 ต้อง authorize Google Drive ก่อนถึงจะซิงก์ได้ (ปุ่มอยู่ด้านล่าง)")

        if st.button("⬇️ ซิงก์เข้า Drive", type="primary",
                     disabled=not pending or not can_sync, width="stretch"):
            prog = st.progress(0.0, text="เริ่มซิงก์...")

            def _tick(i: int, total: int, name: str) -> None:
                prog.progress((i - 1) / max(total, 1), text=f"{i}/{total} — {name}")

            results = flow_sync.sync_folder(watch, QUEUE_ROOT_FOLDER_ID,
                                            max_age_hours=hours, on_progress=_tick,
                                            overrides=overrides, local_root=local_root)
            prog.progress(1.0, text="เสร็จแล้ว")
            ok = sum(1 for r in results if r["ok"])
            (st.success if ok == len(results) else st.warning)(
                f"ซิงก์สำเร็จ {ok}/{len(results)} ไฟล์")
            for r in results:
                st.markdown(f"{'✅' if r['ok'] else '❌'} **{r['name']}** — "
                            f"{r['folder'] if r['ok'] else r['error']}")
            _clear_queue_cache()   # newly filed files must show up straight away
            st.rerun()

        st.divider()
        _render_flow_paste_links()

        st.divider()
        st.markdown("**⚡ ทำให้อัตโนมัติเต็มรูปแบบ**")
        st.caption("1️⃣ รัน watcher ค้างไว้ — ไฟล์ลงปุ๊บจัดเข้าโฟลเดอร์ทันที ไม่ต้องกดปุ่มนี้อีก")
        st.code(f'{Path.cwd() / ".venv/Scripts/python.exe"} {Path.cwd() / "flow_watch.py"}',
                language="powershell")

        st.caption("2️⃣ **ลาก**ปุ่มส้มขึ้นแถบบุ๊กมาร์ก — อย่ากดตรงนี้ ตัวปุ่มไม่ได้สั่งงาน "
                   "มันคือของที่ต้องเอาไปเก็บไว้ พอเก็บแล้วค่อยเปิดโปรเจกต์ใน Flow "
                   "แล้วกดบุ๊กมาร์กอันนั้น มันจะไล่กดดาวน์โหลดให้เอง")
        # ลดจำนวนต่อรอบได้ เผื่ออยากลองน้อย ๆ ก่อนว่าไฟล์มาครบไหม
        # เพดาน 15 ยังเท่าเดิม ปรับขึ้นไม่ได้
        per_run = st.number_input(
            "จำนวนไฟล์ต่อรอบ", min_value=1, max_value=15, value=15, step=1,
            help="ลองตั้งน้อย ๆ ก่อน (เช่น 3) แล้วดูว่าไฟล์มาถึงครบไหม "
                 "ก่อนจะปล่อยเต็ม 15 — ลากบุ๊กมาร์กใหม่ทุกครั้งที่เปลี่ยนเลขนี้")

        try:
            import flow_bookmarklet
            uri = flow_bookmarklet.build("download", max_per_run=int(per_run))
            uri_inspect = flow_bookmarklet.build("inspect")
        except Exception as e:  # noqa: BLE001 — helper file may be missing
            uri = uri_inspect = ""
            st.caption(f"⚠️ สร้างบุ๊กมาร์กเล็ตไม่ได้: {e}")

        if uri:
            # Streamlit ตัด href ที่ขึ้นต้นด้วย javascript: ทิ้งใน st.markdown จึงต้อง
            # วางผ่าน components.html — ลากออกจาก iframe ไปแถบบุ๊กมาร์กได้ตามปกติ
            st.components.v1.html(
                f'''<div style="font:15px system-ui,sans-serif">
                <a href="{html_lib.escape(uri, quote=True)}"
                   style="display:inline-block;background:#F59E0B;color:#111827;
                          font-weight:700;padding:.6rem 1.2rem;border-radius:10px;
                          text-decoration:none;cursor:grab"
                   title="ลากขึ้นแถบบุ๊กมาร์ก — กดตรงนี้ไม่ทำงาน">⬇️ โหลดคลิปจาก Flow</a>
                <a href="{html_lib.escape(uri_inspect, quote=True)}"
                   style="display:inline-block;background:#E5E7EB;color:#374151;
                          font-weight:700;padding:.6rem 1.2rem;border-radius:10px;
                          text-decoration:none;cursor:grab;margin-left:.5rem"
                   title="ลากขึ้นแถบบุ๊กมาร์ก — ใช้ตอนตัวโหลดหาปุ่ม ⋮ ไม่เจอ"
                   >🔎 ตรวจปุ่มในหน้า Flow</a>
                <div style="color:#6B7280;margin-top:.5rem">👆 <b>ลาก</b>ทั้งสองปุ่มขึ้น
                แถบบุ๊กมาร์ก (เปิดแถบด้วย Ctrl+Shift+B) — กดตรงนี้ไม่ทำงาน</div></div>''',
                height=105,
            )
            st.caption("ทำงานในเบราว์เซอร์ปกติที่คุณล็อกอินอยู่แล้ว · หน่วง 3-5 วิต่อไฟล์ · "
                       "สูงสุด 15 ไฟล์ต่อรอบ · กดซ้ำได้ถ้ายังเหลือ")
            st.caption("🔎 ปุ่มสีเทาใช้ตอนตัวโหลดขึ้นว่า **หาปุ่ม ⋮ ไม่เจอ** — มันอ่านอย่างเดียว "
                       "ไม่กดอะไรเลย แล้วขึ้นกล่องข้อความให้กดคัดลอกส่งมาได้ทันที "
                       "ไม่ต้องเปิด Console")

        helper = Path(__file__).parent / "flow_download_helper.js"
        if helper.exists():
            with st.expander("ถ้าลากบุ๊กมาร์กไม่ได้ — ใช้ Console แทน"):
                st.caption("เปิด Flow ใน Chrome → F12 → แท็บ Console → วางสคริปต์นี้ → Enter")
                st.code(helper.read_text(encoding="utf-8"), language="javascript")

        st.caption("ทางเลือก: ตั้งเวลาแทน watcher (ทุก 5 นาที)")
        st.code(
            'schtasks /create /tn "FlowSync" /tr '
            f'"{Path.cwd() / ".venv/Scripts/python.exe"} {Path.cwd() / "flow_sync.py"}" '
            '/sc minute /mo 5',
            language="powershell",
        )


def render_queue_page(line_token: str = "", fb_token: str = "",
                      fb_page_id: str = "", ig_business_id: str = "") -> None:
    _page_head("📁 คิวอนุมัติ", "อ่านไฟล์จาก Google Drive (รวมงานที่สร้างใน Google Flow) → ตรวจ → อนุมัติ → โพสต์")

    lk1, lk2 = st.columns(2)
    with lk1:
        st.link_button("🎬 เปิด Google Flow", FLOW_PROJECT_URL, width="stretch")
    with lk2:
        st.link_button("📁 เปิดโฟลเดอร์ Drive", DRIVE_FOLDER_URL, width="stretch")

    if not GDRIVE_AVAILABLE:
        st.error("ไม่พบ google_drive.py")
        return
    authed = not needs_auth()
    # Show the sync panel even before authorization so the folder and schedule can
    # be set up first; only the upload itself needs Drive access.
    _render_flow_sync(authed)

    if not authed:
        st.warning("ยังไม่ได้ authorize Google Drive")
        if st.button("🔐 Authorize Google Drive", type="primary"):
            with st.spinner("กำลังเปิด browser..."):
                run_first_time_auth()
            st.rerun()
        return

    folders = _cached_child_folders(QUEUE_ROOT_FOLDER_ID)
    if not folders:
        st.warning(
            "มองไม่เห็นโฟลเดอร์ย่อยเลย — น่าจะเป็นเพราะ **OAuth scope เดิม** "
            "(`drive.file` เห็นเฉพาะไฟล์ที่แอปสร้างเอง)"
        )
        st.markdown(
            "**วิธีแก้:** ลบไฟล์ `token.json` ในโฟลเดอร์โปรเจกต์ แล้วกด Authorize ใหม่ "
            "เพื่อให้สิทธิ์แบบเต็ม (`drive`)"
        )
        return

    skip = {"POSTED", "REJECTED"}
    review = {n: i for n, i in folders.items() if n.upper() not in skip}
    st.caption(f"เจอ {len(review)} โฟลเดอร์: " + " · ".join(sorted(review)))

    # ── แคตตาล็อกแยกประเภทสื่อและแพลตฟอร์ม (Media & Platform Catalog) ─────────
    st.markdown("### 🗂️ แคตตาล็อกคิวอนุมัติ (Media Catalog)")
    cat_col1, cat_col2 = st.columns([1, 1])
    with cat_col1:
        media_filter = st.selectbox(
            "🎨 เลือกประเภทสื่อ",
            options=["✨ ทั้งหมด (All Media)", "🎬 วิดีโอ (Videos)", "🖼️ รูปภาพ (Images)", "📝 โพสต์ข้อความ (Captions)"],
            index=0,
            key="queue_media_cat_filter"
        )
    with cat_col2:
        inbox_candidates = [n for n in review if any(k in n for k in ["รอจัดคิว", "Pending Inbox", "Inbox", "รอจัด"])]
        plat_options = ["🌐 ทุกโฟลเดอร์"] + sorted(review.keys())
        default_idx = 0
        if inbox_candidates and inbox_candidates[0] in plat_options:
            default_idx = plat_options.index(inbox_candidates[0])

        plat_filter = st.selectbox(
            "📁 เลือกโฟลเดอร์ / แพลตฟอร์ม",
            options=plat_options,
            index=default_idx,
            key="queue_plat_cat_filter"
        )

    # Folders to display based on platform filter
    if plat_filter == "🌐 ทุกโฟลเดอร์":
        pick = sorted(review.keys())
    else:
        pick = [plat_filter] if plat_filter in review else sorted(review.keys())

    sort_label = st.radio(
        "เรียงลำดับ", ["🆕 ใหม่สุดก่อน", "⏳ เก่าสุดก่อน (ค้างนานสุด)"],
        horizontal=True, label_visibility="collapsed", key="queue_sort",
    )
    oldest_first = sort_label.startswith("⏳")
    if st.button("🔄 โหลดใหม่"):
        # Drop cached previews and collapse every folder back to one page.
        for k in list(st.session_state):
            if k.startswith(("q_data_", "queue_shown_")):
                del st.session_state[k]
        _clear_queue_cache()
        st.rerun()

    total = 0
    for folder_name in pick:
        all_raw_files = _cached_files(review[folder_name], oldest_first)
        if not all_raw_files:
            continue

        # กรองตามประเภทสื่อใน Catalog
        if media_filter.startswith("🎬"):
            files = [f for f in all_raw_files if (f.get("mimeType", "").startswith("video/") or f.get("name", "").lower().endswith((".mp4", ".mov", ".webm", ".avi")))]
        elif media_filter.startswith("🖼️"):
            files = [f for f in all_raw_files if (f.get("mimeType", "").startswith("image/") or f.get("name", "").lower().endswith((".png", ".jpg", ".jpeg", ".webp")))]
        elif media_filter.startswith("📝"):
            files = [f for f in all_raw_files if not (f.get("mimeType", "").startswith(("video/", "image/")) or f.get("name", "").lower().endswith((".mp4", ".mov", ".png", ".jpg", ".webp", ".webm")))]
        else:
            files = all_raw_files

        if not files:
            continue
        platform = _platform_from_folder(folder_name)
        st.divider()
        # Icon only — the folder name already says which platform it is, so the
        # full label would read "🔵 Facebook Facebook VDO". Taken from the Thai
        # label rather than content_studio so the queue works even if that
        # module fails to import.
        icon = PLATFORM_THAI_NAMES.get(platform, "📂").split()[0]

        # Render a page at a time. Streamlit reruns the whole script on every
        # click, so drawing a hundred files means every approve costs a full
        # redraw of all of them.
        shown_key = f"queue_shown_{folder_name}"
        shown = min(st.session_state.get(shown_key, QUEUE_PAGE_SIZE), len(files))

        st.subheader(f"{icon} {folder_name} ({len(files)})")
        if len(files) > shown:
            order = "เก่าสุดก่อน" if oldest_first else "ใหม่สุดก่อน"
            st.caption(f"แสดง {shown} จาก {len(files)} ไฟล์ · เรียง{order}")
        if not platform:
            st.caption("⚠️ เดาแพลตฟอร์มจากชื่อโฟลเดอร์ไม่ได้ — เลือกปลายทางให้แต่ละไฟล์ก่อน")

        _render_batch_review(files[:shown], folder_name, platform)

        for f in files[:shown]:
            total += 1
            _render_queue_file(folder_name, platform, f,
                               line_token, fb_token, fb_page_id, ig_business_id,
                               all_folders=folders,
                               index=total,
                               folder_files=all_raw_files)

        remaining = len(files) - shown
        if remaining > 0:
            more = min(QUEUE_PAGE_SIZE, remaining)
            if st.button(f"⬇️ ดูเพิ่มอีก {more} ไฟล์ (เหลือ {remaining})",
                         key=f"queue_more_{folder_name}", width="stretch"):
                st.session_state[shown_key] = shown + QUEUE_PAGE_SIZE
                st.rerun()

    if total == 0:
        st.success("🎉 ไม่มีงานค้างรออนุมัติ")


# ── Canva (Connect API) ──────────────────────────────────────────────────────────

def _canva_token() -> str:
    """Current Canva access token, refreshed if it's about to expire."""
    tok = st.session_state.get("canva_token")
    if not tok:
        return ""
    if canva_client.token_expired(tok) and tok.get("refresh_token"):
        cid, secret, _ = canva_client.get_credentials()
        new, _msg = canva_client.refresh_token(cid, secret, tok["refresh_token"])
        if new:
            st.session_state["canva_token"] = new
            return new.get("access_token", "")
    return tok.get("access_token", "")


def _render_canva_connect() -> None:
    """Manual OAuth: show the authorize link, take the redirected URL back."""
    cid, secret, redirect_uri = canva_client.get_credentials()
    if not cid or not secret:
        st.warning("ยังไม่ได้ตั้งค่า Canva app")
        st.markdown(
            "**วิธีตั้งค่า** — สร้าง integration ที่ "
            "[canva.com/developers](https://www.canva.com/developers/) แล้วใส่ค่าใน "
            "`.streamlit/secrets.toml`:"
        )
        st.code(
            '[canva]\n'
            'client_id = "ใส่ Client ID"\n'
            'client_secret = "ใส่ Client Secret"\n'
            f'redirect_uri = "{redirect_uri}"',
            language="toml",
        )
        st.caption(f"อย่าลืมตั้ง Redirect URL ใน Canva ให้ตรงกับ `{redirect_uri}`")
        return

    if "canva_pkce" not in st.session_state:
        st.session_state["canva_pkce"] = canva_client.make_pkce()
    verifier, challenge = st.session_state["canva_pkce"]
    auth_url = canva_client.build_auth_url(cid, redirect_uri, challenge)

    st.markdown(f"**1.** [🔗 กดที่นี่เพื่ออนุญาตให้แอปเข้าถึง Canva]({auth_url})")
    st.caption("**2.** อนุญาตแล้ว Canva จะพาไปหน้าที่ URL มี `?code=...` — copy URL นั้นทั้งอัน")
    pasted = st.text_input("**3.** วาง URL ที่ถูก redirect มาที่นี่", key="canva_redirect_url")
    if st.button("เชื่อมต่อ Canva", type="primary", disabled=not pasted):
        code = canva_client.extract_code(pasted)
        if not code:
            st.error("ไม่พบ `code=` ใน URL — ตรวจสอบว่า copy มาครบทั้ง URL")
            return
        with st.spinner("กำลังเชื่อมต่อ..."):
            tok, msg = canva_client.exchange_code(cid, secret, code, verifier, redirect_uri)
        if tok:
            st.session_state["canva_token"] = tok
            st.session_state.pop("canva_pkce", None)
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)


def _render_canva_autofill(token: str, caps: dict) -> None:
    """Brand template → autofill → export. Enterprise-only."""
    if not caps.get("brand_templates"):
        st.warning(
            "⚠️ บัญชี Canva นี้ใช้ **Autofill / Brand Template ไม่ได้** — "
            "Canva กำหนดให้ต้องเป็นแพลน **Enterprise** เท่านั้น"
        )
        if caps.get("note"):
            st.caption(caps["note"])
        st.markdown(
            "**ทางเลือกที่ใช้ได้เลยตอนนี้:** ส่งรูปที่ AI สร้างขึ้นไปเก็บใน Canva "
            "แล้วเปิดแต่งต่อเองในเว็บ (ดูหัวข้อด้านล่าง)"
        )
        return

    templates, err = canva_client.list_brand_templates(token)
    if err:
        st.error(err)
        return
    if not templates:
        st.info("ยังไม่มี Brand Template ในบัญชีนี้ — สร้างในเว็บ Canva ก่อน")
        return

    tmap = {t["title"]: t["id"] for t in templates}
    picked = st.selectbox("เลือก Brand Template", options=list(tmap.keys()))
    tid = tmap[picked]

    fields, derr = canva_client.get_template_dataset(token, tid)
    if derr:
        st.error(derr)
        return
    if not fields:
        st.info("เทมเพลตนี้ไม่มีช่องที่เติมข้อมูลได้")
        return

    st.caption(f"เทมเพลตนี้มี {len(fields)} ช่อง")
    values: dict = {}
    for fname, meta in fields.items():
        ftype = (meta or {}).get("type", "text")
        if ftype == "image":
            st.caption(f"🖼️ `{fname}` — ช่องรูป (ใช้รูปที่สร้างจากแชท)")
            img = st.session_state.get("canva_pending_image")
            if img:
                st.image(img, width=120)
                values[fname] = "__PENDING_IMAGE__"
            else:
                st.caption("ยังไม่มีรูป — สร้างรูปในหน้า Copilot แล้วกด 'ส่งไป Canva'")
        else:
            values[fname] = st.text_input(f"📝 {fname}", key=f"canva_f_{fname}")

    title = st.text_input("ชื่อดีไซน์", value=f"LEMED {dt.datetime.now():%d/%m %H:%M}")

    if st.button("🎨 สร้างดีไซน์จากเทมเพลต", type="primary", width="stretch"):
        with st.spinner("กำลังอัปโหลดรูป / สร้างดีไซน์..."):
            # Any image field needs a Canva asset id, so upload first.
            img = st.session_state.get("canva_pending_image")
            for k, v in list(values.items()):
                if v == "__PENDING_IMAGE__":
                    if not img:
                        values.pop(k)
                        continue
                    asset_id, amsg = canva_client.upload_asset(
                        token, img, f"lemed_{dt.datetime.now():%Y%m%d_%H%M%S}.png")
                    if not asset_id:
                        st.error(amsg)
                        return
                    values[k] = asset_id

            data = canva_client.build_autofill_data(fields, values)
            design, msg = canva_client.autofill(token, tid, data, title)

        if not design:
            st.error(msg)
            return
        st.success(msg)
        url = (design.get("urls") or {}).get("edit_url") or design.get("url", "")
        if url:
            st.markdown(f"[🔗 เปิดดีไซน์ใน Canva]({url})")

        design_id = design.get("id", "")
        if design_id:
            with st.spinner("กำลัง export เป็นรูป..."):
                urls, emsg = canva_client.export_design(token, design_id, "png")
            if urls:
                st.success(emsg)
                for i, u in enumerate(urls, 1):
                    data_bytes = canva_client.download(u)
                    if data_bytes:
                        st.image(data_bytes, caption=f"หน้า {i}", width="stretch")
                        st.download_button(
                            f"📥 ดาวน์โหลดหน้า {i}", data=data_bytes,
                            file_name=f"canva_{design_id}_{i}.png", mime="image/png",
                            key=f"canva_dl_{design_id}_{i}", width="stretch")
            else:
                st.warning(emsg)


def render_canva_page() -> None:
    _page_head("🎨 Canva", "เชื่อม Canva Connect API — เติมข้อมูลลง Brand Template แล้ว export เป็นโปสเตอร์/carousel")

    if not CANVA_AVAILABLE:
        st.error("ไม่พบ canva_client.py — ตรวจสอบไฟล์ในโฟลเดอร์โปรเจกต์")
        return

    token = _canva_token()
    if not token:
        _render_canva_connect()
        return

    with st.spinner("กำลังเช็คสิทธิ์บัญชี..."):
        caps = st.session_state.get("canva_caps") or canva_client.capabilities(token)
        st.session_state["canva_caps"] = caps

    if not caps.get("connected"):
        st.error(caps.get("note") or "token ใช้ไม่ได้")
        if st.button("🔌 เชื่อมต่อใหม่"):
            for k in ("canva_token", "canva_caps", "canva_pkce"):
                st.session_state.pop(k, None)
            st.rerun()
        return

    head, btn = st.columns([3, 1])
    with head:
        badge = "✅ Enterprise (ใช้ Autofill ได้)" if caps.get("brand_templates") \
            else "⚠️ ไม่ใช่ Enterprise (Autofill ใช้ไม่ได้)"
        st.success(f"เชื่อม Canva แล้ว — {badge}")
    with btn:
        if st.button("ตัดการเชื่อมต่อ", width="stretch"):
            for k in ("canva_token", "canva_caps", "canva_pkce"):
                st.session_state.pop(k, None)
            st.rerun()

    st.divider()
    st.subheader("🖼️ สร้างจาก Brand Template")
    _render_canva_autofill(token, caps)

    st.divider()
    st.subheader("📤 ส่งรูปเข้าคลัง Canva")
    st.caption("ใช้ได้ทุกแพลน — อัปรูปที่ AI สร้างเข้า Canva แล้วเปิดแต่งต่อในเว็บ")
    img = st.session_state.get("canva_pending_image")
    if img:
        st.image(img, width=180, caption="รูปที่รอส่ง (จากหน้า Copilot)")
        if st.button("📤 อัปโหลดเข้า Canva", width="stretch"):
            with st.spinner("กำลังอัปโหลด..."):
                asset_id, msg = canva_client.upload_asset(
                    token, img, f"lemed_{dt.datetime.now():%Y%m%d_%H%M%S}.png")
            if asset_id:
                st.success(f"{msg} — เปิด Canva แล้วหาในแท็บ Uploads ได้เลย")
                st.markdown("[🔗 เปิด Canva](https://www.canva.com/)")
            else:
                st.error(msg)
    else:
        st.info("ยังไม่มีรูป — ไปหน้า 🗨️ แชท AI สร้างรูปแล้วกด **ส่งไป Canva**")


# ── Brain Storm (Business Model Canvas) ──────────────────────────────────────────

def _send_idea_to_copilot(prompt: str) -> None:
    """Hand an idea to the Chat Copilot and jump to that page."""
    st.session_state["copilot_pending"] = prompt
    st.session_state["shop_menu"] = "🗨️ แชท AI"


def render_brainstorm_page(ai_mode: str, api_key: str) -> None:
    _page_head("🧠 Brain Storm", "อธิบายธุรกิจ → ร่าง Business Model Canvas → ได้ไอเดียคอนเทนต์ ส่งเข้า Copilot ได้เลย")

    if not BRAINSTORM_AVAILABLE:
        st.error("ไม่พบ brainstorm.py — ตรวจสอบไฟล์ในโฟลเดอร์โปรเจกต์")
        return

    _key, _provider, _label = _resolve_ai(ai_mode, api_key)
    st.caption(_label)
    _mandala_badge()
    brand_ctx = brainstorm.load_brand_context()

    desc = st.text_area(
        "ธุรกิจของคุณ",
        value=st.session_state.get("bs_desc", brainstorm.DEFAULT_BUSINESS),
        height=100,
        key="bs_desc",
        help="ยิ่งอธิบายละเอียด (สินค้า/กลุ่มเป้าหมาย/จุดขาย) ผลลัพธ์ยิ่งตรง",
    )

    gen_col, clr_col = st.columns([3, 1])
    with gen_col:
        if st.button("🧠 ร่าง Business Model Canvas", type="primary", width="stretch"):
            with st.spinner("กำลังร่าง BMC..."):
                st.session_state["bs_bmc"] = brainstorm.generate_bmc(
                    desc, _key, brand_ctx, _provider)
            st.session_state.pop("bs_ideas", None)
            st.rerun()
    with clr_col:
        if "bs_bmc" in st.session_state and st.button("🗑️ ล้าง", width="stretch"):
            st.session_state.pop("bs_bmc", None)
            st.session_state.pop("bs_ideas", None)
            st.rerun()

    bmc = st.session_state.get("bs_bmc")
    if not bmc:
        st.info("💡 กรอกข้อมูลธุรกิจแล้วกดปุ่มด้านบน เพื่อร่าง BMC 9 ช่อง")
        return

    st.divider()
    st.subheader("📋 Business Model Canvas")
    st.caption("แก้ไขได้ทุกช่อง — ไอเดียคอนเทนต์จะอิงจากที่แก้ล่าสุด")

    cols = st.columns(3)
    for i, (bkey, label, question) in enumerate(brainstorm.BMC_BLOCKS):
        with cols[i % 3]:
            with st.container(border=True):
                st.markdown(f"**{label}**")
                st.caption(question)
                bmc[bkey] = st.text_area(
                    label, value=bmc.get(bkey, ""), height=110,
                    key=f"bs_block_{bkey}", label_visibility="collapsed",
                )
    st.session_state["bs_bmc"] = bmc

    st.divider()
    st.subheader("💡 ไอเดียคอนเทนต์")

    n_ideas = st.slider("จำนวนไอเดีย", 2, 6, 4, key="bs_n")
    if st.button("✨ เสนอไอเดียจาก BMC", width="stretch"):
        with st.spinner("กำลังคิดไอเดีย..."):
            st.session_state["bs_ideas"] = brainstorm.generate_ideas(
                bmc, desc, _key, n_ideas, brand_ctx, _provider)
        st.rerun()

    ideas = st.session_state.get("bs_ideas")
    if not ideas:
        st.info("กดปุ่มด้านบนเพื่อให้ AI เสนอไอเดียคอนเทนต์จาก BMC")
        return

    for idx, idea in enumerate(ideas):
        with st.container(border=True):
            st.markdown(f"**{idea['title']}**")
            if idea.get("rationale"):
                st.caption(idea["rationale"])
            plats = " · ".join(
                f"{PLATFORMS[p]['icon']} {PLATFORMS[p]['name']}"
                for p in idea["platforms"] if p in PLATFORMS
            )
            st.markdown(f"<span style='font-size:12.5px;opacity:.75'>{plats} — โทน {idea['tone']}</span>",
                        unsafe_allow_html=True)
            st.code(idea["prompt"], language=None)
            st.button(
                "🗨️ ส่งเข้า Copilot เพื่อร่างคอนเทนต์",
                key=f"bs_send_{idx}",
                width="stretch",
                on_click=_send_idea_to_copilot,
                args=(idea["prompt"],),
            )


# ── Chat Copilot ─────────────────────────────────────────────────────────────────

def _copilot_examples() -> list[tuple[str, str]]:
    """(label, target) for the three suggestions under the composer.

    Everyday phrasing, not marketing vocabulary — examples double as
    instructions here, and someone unsure what to type copies their shape.

    Two of the three name jobs this page cannot do: replying to customers lives
    in AI Inbox, sales analysis lives in the Dashboard. Rather than drop the
    wording or let it produce a content draft that answers neither, `target`
    routes the click to the page that actually does the work. Four suggestions
    became three: past that, a shortcut row reads as a menu to be read rather
    than an example to be copied.
    """
    return [
        ("เขียนโพสต์ขายสินค้า", ""),
        ("ตอบแชทลูกค้า", "💬 AI Inbox"),
        ("วิเคราะห์ยอดขาย", "📊 Dashboard"),
    ]


_ATTACH_ICONS = {"image": "🖼️", "pdf": "📄", "table": "📊",
                 "text": "📝", "unsupported": "📎"}


def _can_read_media(key: str, provider: str) -> bool:
    """Whether the active key can look at a picture. False without ai_provider."""
    try:
        import ai_provider
        return ai_provider.can_read_media(key, provider)
    except Exception:  # noqa: BLE001
        return False


def _render_message_attachments(files: list, mi: int) -> None:
    """Show what was attached, inside the user's own bubble.

    Images render; everything else gets a chip. Only image bytes are kept in
    session state — a 5MB spreadsheet held for the life of the conversation buys
    nothing once it has been summarised.
    """
    if not files:
        return
    images = [(n, data) for n, kind, data in files if kind == "image" and data]
    others = [(n, kind) for n, kind, data in files if not (kind == "image" and data)]
    if images:
        # Fixed width, not "stretch": one attached photo stretched to the full
        # 900px column and buried the message it was attached to.
        cols = st.columns(3)
        for i, (name, data) in enumerate(images):
            with cols[i % 3]:
                st.image(data, caption=name, width=240)
    if others:
        _chips([(f"{_ATTACH_ICONS.get(kind, '📎')} {name}", "") for name, kind in others])


def _run_suggestion(label: str, target: str) -> None:
    """Send a suggestion to the copilot, or open the page that handles it.

    Navigation goes through `nav_to` rather than writing `shop_menu` directly:
    Streamlit refuses to let a widget's key be reassigned once that widget has
    been instantiated this run, and the sidebar radio is always instantiated
    before the page body renders. The sidebar drains `nav_to` on the next run,
    before it builds the radio, where the assignment is legal.
    """
    if target:
        st.session_state["nav_to"] = target
    else:
        st.session_state["copilot_pending"] = label
    st.rerun()


def _copilot_send_to_queue(pid: str, content: str, brief: dict,
                           img_bytes: bytes = None, vid_bytes: bytes = None) -> None:
    """Write a pending draft AND attached media (video/image) into its per-platform Drive folder.

    Drive is the queue — the ✋ คิวอนุมัติ page reads straight from those folders,
    so there is no second list to keep in sync here.
    """
    if not GDRIVE_AVAILABLE or needs_auth():
        st.warning("ยังไม่ได้ต่อ Google Drive — ไปที่หน้า ✋ คิวอนุมัติ เพื่อ authorize ก่อน")
        return

    # ส่งเข้าโฟลเดอร์กลาง '📥 รอจัดคิว (Pending Inbox)' เพื่อให้ผู้ใช้เลือกแพลตฟอร์มในหน้าคิวอนุมัติ
    try:
        from google_drive import ensure_subfolder
        inbox_folder = ensure_subfolder(QUEUE_ROOT_FOLDER_ID, "📥 รอจัดคิว (Pending Inbox)")
        target_folder, routed = (inbox_folder or QUEUE_ROOT_FOLDER_ID), True
    except Exception:
        target_folder, routed = QUEUE_ROOT_FOLDER_ID, False

    ts = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
    import hashlib
    
    # 1. อัปโหลดไฟล์วิดีโอ/รูปภาพก่อน
    media_uploaded = []
    if vid_bytes and len(vid_bytes) > 1000:
        sn_val = f"LMD-VDO-{hashlib.md5(vid_bytes[:500]).hexdigest()[:6].upper()}"
        fname_vid = f"PENDING_{pid}_{sn_val}_{ts}.mp4"
        link_vid = upload_file(vid_bytes, fname_vid, target_folder, mime_type="video/mp4")
        if link_vid:
            media_uploaded.append(f"[🎬 ไฟล์วิดีโอ `{sn_val}` ({len(vid_bytes)/1024/1024:.1f} MB)]({link_vid})")
    elif img_bytes:
        sn_val = f"LMD-IMG-{hashlib.md5(img_bytes[:500]).hexdigest()[:6].upper()}"
        fname_img = f"PENDING_{pid}_{sn_val}_{ts}.png"
        link_img = upload_file(img_bytes, fname_img, target_folder, mime_type="image/png")
        if link_img:
            media_uploaded.append(f"[🖼️ ไฟล์รูปภาพ `{sn_val}`]({link_img})")
    else:
        sn_val = f"LMD-POST-{hashlib.md5(content.encode()).hexdigest()[:6].upper()}"

    # 2. อัปโหลดแคปชันข้อความ
    fname_txt = f"PENDING_{pid}_{sn_val}_{ts}.txt"
    link_txt = upload_text(content, fname_txt, target_folder)

    # 3. ล้างแคชเพื่อให้ไฟล์ใหม่ปรากฏในหน้าคิวตรวจทันที
    _clear_queue_cache()

    where = "📥 รอจัดคิว (Pending Inbox)"
    st.success(f"🎉 ส่งข้อความ{' + วิดีโอ' if vid_bytes else (' + รูปภาพ' if img_bytes else '')} เข้าสู่ **{where}** เรียบร้อยแล้ว!")
    links_str = " · ".join([f"[📝 แคปชัน]({link_txt})"] + media_uploaded)
    st.markdown(f"🔗 **ไฟล์ใน Drive:** {links_str}")
    st.info("👉 คุณสามารถคลิกเมนู **✋ คิวอนุมัติ** ที่แถบด้านซ้าย เพื่อเลือกแพลตฟอร์มและอนุมัติโพสต์ได้ทันทีครับ")


def _angle_picker(mi: int, scene: str, medium: str, label: str) -> str:
    """Let the user pick how the scene is told, for one medium.

    The list is medium-specific: an angle only appears where it has material, so
    "3 เหตุผล" is offered for a clip and a carousel but not for a single frame.
    """
    if not SCENES_AVAILABLE:
        return ""
    options = scene_presets.angles_for(scene, medium)
    chosen = st.radio(label, options=options,
                      format_func=scene_presets.angle_label, horizontal=True,
                      key=f"copilot_angle_{medium}_{mi}")
    st.caption(f"🎯 {scene_presets.angle_goal(chosen)}")
    return chosen


def _render_copilot_image(mi: int, brief: dict, scene: str,
                          gemini_key: str) -> bytes | None:
    """Image block: show the prompt, and let Gemini actually render it.

    Returns the generated image bytes (if any) so posting can attach them.
    """
    img_key = f"copilot_img_{mi}"
    with st.expander("🖼️ ภาพประกอบ — Master Prompt", expanded=bool(st.session_state.get(img_key))):
        angle = _angle_picker(mi, scene, "image", "🖼️ แบบของภาพ — เลือกได้หลายแบบในหมวดเดียวกัน")
        image_prompt = content_copilot.build_master_image_prompt(brief, scene, angle)
        st.caption("📋 คัดลอกไปวางใน Google Flow / Midjourney ได้เลย (กดไอคอนคัดลอกมุมขวาบน)")
        st.code(image_prompt, language=None)
        c_flow1, c_flow2 = st.columns([1, 1])
        with c_flow1:
            st.link_button("🎬 เปิด Google Flow เอง", FLOW_PROJECT_URL, width="stretch")
        with c_flow2:
            if st.button("🤖 สั่งบอทสร้างใน Flow", key=f"copilot_bot_img_{mi}", width="stretch"):
                try:
                    import flow_queue
                    import time
                    task_id = flow_queue.submit_request(image_prompt, media_type="image")
                    status_slot = st.empty()
                    with st.spinner("🤖 บอทกำลังส่งคำสั่งไป Google Flow..."):
                        for attempt in range(80): # 80 x 2.5s = 200s
                            task = flow_queue.get_request_status(task_id)
                            status_val = task.get("status") if task else "PENDING"
                            if status_val == "PROCESSING":
                                status_slot.info(f"🎨 บอทกำลังวาดรูปใน Google Flow... ({attempt * 2}s)")
                            if task and task.get("status") == "DONE":
                                st.success("🎉 บอทสร้างใน Google Flow เรียบร้อย!")
                                media_b = task.get("media_bytes")
                                if media_b:
                                    st.session_state[img_key] = media_b
                                    st.rerun()
                                else:
                                    res_path = task.get("result_path")
                                    if res_path and Path(res_path).exists():
                                        st.session_state[img_key] = Path(res_path).read_bytes()
                                        st.rerun()
                                break
                            elif task and task.get("status") == "ERROR":
                                st.error(f"❌ ข้อผิดพลาด: {task.get('error_message')}")
                                break
                            time.sleep(2)
                except Exception as e:
                    st.error(f"เรียกบอทไม่สำเร็จ: {e}")

        if gemini_key:
            if st.button("✨ สร้างรูปด้วย Gemini", key=f"copilot_genimg_{mi}",
                         width="stretch"):
                import ai_provider
                with st.spinner("กำลังสร้างรูป... (10-30 วินาที)"):
                    img_bytes, msg = ai_provider.generate_image(image_prompt, gemini_key)
                if img_bytes:
                    st.session_state[img_key] = img_bytes
                    st.toast(msg, icon="✅")
                    st.rerun()
                else:
                    st.error(msg)
        else:
            st.caption("💡 ใส่ **Gemini API key** ในแถบซ้าย แล้วจะสร้างรูปได้จากในแชทเลย")

        img = st.session_state.get(img_key)
        if img:
            st.image(img, caption="ภาพที่สร้างด้วย Gemini", width="stretch")
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.download_button("📥 ดาวน์โหลด", data=img,
                                   file_name=f"lemed_{mi}.png", mime="image/png",
                                   key=f"copilot_dlimg_{mi}", width="stretch")
            with c2:
                if st.button("📁 ส่งเข้า Catalog", key=f"copilot_img_to_cat_{mi}", width="stretch"):
                    _copilot_send_to_queue("all", f"รูปภาพสำหรับแคมเปญ {brief.get('campaign', 'LEMED')}", brief, img_bytes=img)
            with c3:
                if CANVA_AVAILABLE and st.button("🎨 ส่งไป Canva",
                                                 key=f"copilot_canva_{mi}",
                                                 width="stretch"):
                    st.session_state["canva_pending_image"] = img
                    st.session_state["shop_menu"] = "🎨 Canva"
                    st.rerun()
            with c4:
                if st.button("🗑️ ลบรูป", key=f"copilot_rmimg_{mi}", width="stretch"):
                    del st.session_state[img_key]
                    st.rerun()
        return img
    return None


def _render_copilot_video(mi: int, brief: dict, scene: str, aspect: str,
                          gemini_key: str) -> bytes | None:
    """Video block: prompt, cost estimate, generate with Veo, preview in chat."""
    import ai_provider

    vid_key = f"copilot_vid_{mi}"
    with st.expander("🎬 วิดีโอ — Master Prompt", expanded=bool(st.session_state.get(vid_key))):
        # The scene fixes where the clip is shot; the angle picks how it is told,
        # so the same scene yields several genuinely different videos.
        angle = _angle_picker(mi, scene, "video",
                              "🎞️ แนวการเล่าเรื่อง — เลือกได้หลายแบบในหมวดเดียวกัน")
        if SCENES_AVAILABLE and not scene_presets.has_people(scene):
            st.caption("📦 หมวดนี้ไม่มีคนในภาพ แนวที่ต้องมีตัวแสดง (รีวิว, สาธิต, "
                       "ก่อน-หลัง) จึงไม่ขึ้นให้เลือก")

        st.caption(f"📋 คัดลอกไปวางใน Google Flow ได้เลย · สัดส่วน {aspect} · "
                   "10 วินาที · Hook → Decision → CTA · เสียงพากย์ไทย")
        video_prompt = content_copilot.build_master_video_prompt(brief, scene, 10, angle)
        st.code(video_prompt, language=None)
        c_vflow1, c_vflow2 = st.columns([1, 1])
        with c_vflow1:
            st.link_button("🎬 เปิด Google Flow เอง", FLOW_PROJECT_URL, width="stretch")
        with c_vflow2:
            if st.button("🤖 สั่งบอทสร้างใน Flow", key=f"copilot_bot_vid_{mi}", width="stretch"):
                try:
                    import flow_queue
                    import time
                    task_id = flow_queue.submit_request(video_prompt, media_type="video")
                    status_slot = st.empty()
                    with st.spinner("🤖 บอทกำลังส่งคำสั่งไป Google Flow..."):
                        for attempt in range(120): # 120 x 2.5s = 300s (5 นาที)
                            task = flow_queue.get_request_status(task_id)
                            status_val = task.get("status") if task else "PENDING"
                            if status_val == "PROCESSING":
                                status_slot.info(f"🎬 บอทกำลังเรนเดอร์วิดีโอใน Google Flow... (ปกติ 1-3 นาที) [{attempt * 2}s]")
                            if task and task.get("status") == "DONE":
                                status_slot.success("🎉 บอทสร้างใน Google Flow เรียบร้อย!")
                                media_b = task.get("media_bytes")
                                if not media_b and task.get("drive_file_id"):
                                    # Fallback download directly
                                    try:
                                        media_b = flow_queue.get_request_status(task_id).get("media_bytes")
                                    except Exception:
                                        pass
                                if media_b:
                                    st.session_state[vid_key] = media_b
                                    st.rerun()
                                else:
                                    res_path = task.get("result_path")
                                    if res_path and Path(res_path).exists():
                                        st.session_state[vid_key] = Path(res_path).read_bytes()
                                        st.rerun()
                                break
                            elif task and task.get("status") == "ERROR":
                                st.error(f"❌ ข้อผิดพลาด: {task.get('error_message')}")
                                break
                            time.sleep(2)
                except Exception as e:
                    st.error(f"เรียกบอทไม่สำเร็จ: {e}")

        if gemini_key:
            st.info("ℹ️ Veo สร้างได้สูงสุด **8 วินาที** ต่อคลิป — ตัว Master Prompt ด้านบน "
                    "เป็นเวอร์ชัน 10 วินาทีสำหรับ Google Flow (ต่อคลิปได้)")
            c1, c2 = st.columns(2)
            with c1:
                tier = st.selectbox(
                    "คุณภาพ", options=["fast", "standard"],
                    format_func=lambda t: {"fast": "⚡ Fast (ถูกกว่า)",
                                           "standard": "💎 Standard (คมกว่า)"}[t],
                    key=f"copilot_vtier_{mi}",
                )
            with c2:
                secs = st.selectbox("ความยาว", options=[4, 6, 8], index=2,
                                    format_func=lambda s: f"{s} วินาที",
                                    key=f"copilot_vsec_{mi}")

            cost = ai_provider.estimate_video_cost(secs, tier)
            st.warning(f"💰 คลิปนี้มีค่าใช้จ่ายประมาณ **${cost:.2f}** "
                       f"({secs} วิ · {tier}) — คิดเงินเฉพาะตอนสร้างสำเร็จ")

            if st.button("🎬 สร้างวิดีโอด้วย Veo", key=f"copilot_genvid_{mi}",
                         width="stretch"):
                status = st.empty()
                with st.spinner("กำลังสร้างวิดีโอ... (ปกติ 1-3 นาที อย่าปิดหน้านี้)"):
                    vid, msg = ai_provider.generate_video(
                        content_copilot.build_master_video_prompt(brief, scene, secs, angle),
                        gemini_key, tier=tier, seconds=secs,
                        aspect_ratio=aspect, on_progress=status.info,
                    )
                status.empty()
                if vid:
                    st.session_state[vid_key] = vid
                    st.toast(msg, icon="✅")
                    st.rerun()
                else:
                    st.error(msg)
        else:
            st.caption("💡 ใส่ **Gemini API key** ในแถบซ้าย แล้วจะสร้างวิดีโอได้จากในแชท")

        vid = st.session_state.get(vid_key)
        if vid and len(vid) > 1000:
            import hashlib
            sn_key = f"sn_vid_{mi}"
            if sn_key not in st.session_state:
                h_val = hashlib.md5(vid[:500] if isinstance(vid, (bytes, bytearray)) else f"{mi}_{time.time()}".encode()).hexdigest()[:6].upper()
                st.session_state[sn_key] = f"LMD-VDO-{h_val}"
            vid_sn = st.session_state[sn_key]

            st.info(f"🏷️ **Serial Number:** `{vid_sn}`  (รหัสนี้จะส่งต่อไปยังหน้าคิวอนุมัติ)")
            import tempfile, os
            tmp_path = os.path.join(tempfile.gettempdir(), f"st_video_cache_{vid_sn}.mp4")
            if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) != len(vid):
                with open(tmp_path, "wb") as f:
                    f.write(vid)
            st.video(tmp_path)
            st.caption(f"ขนาดไฟล์ {len(vid)/1024/1024:.1f} MB · รหัสวิดีโอ: **{vid_sn}**")
            d1, d2, d3 = st.columns(3)
            with d1:
                st.download_button(f"📥 ดาวน์โหลดวิดีโอ ({vid_sn})", data=vid,
                                   file_name=f"{vid_sn}.mp4", mime="video/mp4",
                                   key=f"copilot_dlvid_{mi}", width="stretch")
            with d2:
                if st.button("📁 ส่งวิดีโอเข้า Catalog", key=f"copilot_vid_to_cat_{mi}", width="stretch"):
                    _copilot_send_to_queue("all", f"วิดีโอสำหรับแคมเปญ {brief.get('campaign', 'LEMED')} ({vid_sn})", brief, vid_bytes=vid)
            with d3:
                if st.button("🗑️ ลบวิดีโอ", key=f"copilot_rmvid_{mi}",
                             width="stretch"):
                    del st.session_state[vid_key]
                    st.rerun()
        return vid
    return None


def _render_copilot_carousel(mi: int, brief: dict, scene: str, gemini_key: str) -> None:
    """Poster carousel: per-slide Thai copy + master prompt, optional batch render."""
    key_all = f"copilot_car_{mi}"

    with st.expander("🖼️ โปสเตอร์ Carousel (5 สไลด์) — Master Prompt"):
        angle = _angle_picker(mi, scene, "carousel",
                              "📑 โครงเรื่องของชุดสไลด์ — เลือกได้หลายแบบในหมวดเดียวกัน")
        slides = content_copilot.build_carousel(brief, scene, 5, angle)
        # Name the arc from the slides themselves, so a different angle does not
        # keep advertising the default Hook → ปัญหา → ทางออก shape.
        st.caption("เล่าเรื่องต่อกันเป็นชุด: "
                   + " → ".join(s["label"].split(" ", 1)[-1] for s in slides)
                   + " · สัดส่วน 4:5")

        if gemini_key:
            if st.button(f"✨ สร้างรูปทั้ง {len(slides)} สไลด์ด้วย Gemini",
                         key=f"copilot_genall_{mi}", width="stretch"):
                import ai_provider
                imgs, prog = {}, st.progress(0.0, text="เริ่มสร้าง...")
                for idx, s in enumerate(slides):
                    prog.progress(idx / len(slides),
                                  text=f"สไลด์ {s['n']}/{len(slides)} — {s['label']}")
                    img, msg = ai_provider.generate_image(s["prompt"], gemini_key)
                    if img:
                        imgs[s["n"]] = img
                    else:
                        st.warning(f"สไลด์ {s['n']}: {msg}")
                prog.progress(1.0, text="เสร็จแล้ว")
                st.session_state[key_all] = imgs
                st.rerun()
        else:
            st.caption("💡 ใส่ Gemini API key เพื่อสร้างรูปทุกสไลด์รวดเดียว")

        # Tabs, not a popover per slide. Each prompt is 32 lines, which rendered a
        # ~500px floating panel anchored to a button already near the bottom of an
        # open expander — it opened below the fold, moved with the page as you
        # scrolled after it, and left its own close target off screen. Tabs put the
        # same content in the page flow, where there is nothing to chase or close.
        made = st.session_state.get(key_all, {})
        for tab, s in zip(st.tabs([f"{s['n']}. {s['label']}" for s in slides]), slides):
            with tab:
                st.caption(s["purpose"])
                st.markdown(f"> **{s['headline_th']}**  \n> {s['sub_th']}")
                img = made.get(s["n"])
                if img:
                    st.image(img, width="stretch")
                    st.download_button(
                        f"📥 ดาวน์โหลดสไลด์ {s['n']}", data=img,
                        file_name=f"carousel_{mi}_{s['n']}.png", mime="image/png",
                        key=f"copilot_cardl_{mi}_{s['n']}", width="stretch")
                st.code(s["prompt"], language=None)
                c_cflow1, c_cflow2 = st.columns([1, 1])
                with c_cflow1:
                    st.link_button("🎬 เปิด Google Flow เอง", FLOW_PROJECT_URL, width="stretch")
                with c_cflow2:
                    if st.button("🤖 สั่งบอทสร้างใน Flow", key=f"copilot_bot_car_{mi}_{s['n']}", width="stretch"):
                        try:
                            import flow_queue
                            import time
                            task_id = flow_queue.submit_request(s["prompt"], media_type="image")
                            with st.spinner("🤖 บอทกำลังส่งคำสั่งไป Google Flow..."):
                                for _ in range(45):
                                    task = flow_queue.get_request_status(task_id)
                                    if task and task.get("status") == "DONE":
                                        st.success("🎉 บอทป้อนคำสั่งและสร้างใน Google Flow แล้ว!")
                                        time.sleep(1)
                                        break
                                    elif task and task.get("status") == "ERROR":
                                        st.error(f"❌ ข้อผิดพลาด: {task.get('error_message')}")
                                        break
                                    time.sleep(2)
                        except Exception as e:
                            st.error(f"เรียกบอทไม่สำเร็จ: {e}")


def _render_copilot_draft(mi: int, brief: dict, package: dict,
                          line_token: str, fb_token: str, fb_page_id: str,
                          ig_business_id: str, gemini_key: str = "") -> None:
    """Render one assistant draft: summary + editable content + approve/queue."""
    campaign_label = CAMPAIGN_TYPES.get(brief.get("campaign", ""), {}).get(
        "label", brief.get("campaign", "")
    )
    summary = brief.get("summary") or content_copilot.describe(brief)
    st.markdown(f"ร่างให้แล้วค่ะ ✨ — **{campaign_label}**")
    if summary:
        st.caption(summary)

    plats = [p for p in brief.get("platforms", []) if p in package and p in PLATFORMS]
    if not plats:
        st.warning("ยังไม่มีแพลตฟอร์มที่ร่างได้ — ลองพิมพ์ระบุแพลตฟอร์มเพิ่มดูนะ (เช่น IG, LINE)")
        return

    # Scene picker — one choice drives both the image and video master prompts so
    # a campaign's stills and clip stay visually consistent.
    scene = scene_presets.DEFAULT_SCENE
    if SCENES_AVAILABLE:
        # Order by how well each angle fits this brand's own material, so the
        # most relevant scenes are the ones read first.
        scores = _scene_scores()
        choices = scene_presets.scene_choices()
        if scores:
            choices = sorted(choices, key=lambda k: (-scores[k], scene_presets.label_for(k)))
            default_index = 0
        else:
            default_index = (choices.index(scene_presets.DEFAULT_SCENE)
                             if scene_presets.DEFAULT_SCENE in choices else 0)

        def _scene_label(k: str) -> str:
            n = scores.get(k, 0)
            stars = f"{'★' * n}{'·' * (5 - n)} " if n else ""
            return f"{stars}{scene_presets.label_for(k)}"

        sc_col, sc_info = st.columns([2, 1])
        with sc_col:
            scene = st.selectbox(
                "🎯 หมวด / ฉากของภาพและวิดีโอ",
                options=choices,
                index=default_index,
                format_func=_scene_label,
                key=f"copilot_scene_{mi}",
            )
        with sc_info:
            st.caption(scene_presets.group_for(scene))
            if scene_presets.has_people(scene):
                st.caption("👤 มีคนในภาพ")

        goal = scene_presets.goal_for(scene)
        if goal:
            st.info(f"**เป้าหมายของหมวดนี้:** {goal}")
        if scores.get(scene):
            st.caption(
                f"{'★' * scores[scene]}{'·' * (5 - scores[scene])} "
                "ความเข้ากับแบรนด์ — วัดจากที่บริบทและคอนเทนต์เดิมใน Mandala AI "
                "พูดถึงมุมนี้บ่อยแค่ไหน (ไม่ใช่การทำนายยอด engagement)"
            )

    img_bytes = _render_copilot_image(mi, brief, scene, gemini_key)

    _render_copilot_carousel(mi, brief, scene, gemini_key)

    vid_bytes = _render_copilot_video(
        mi, brief, scene, content_copilot.video_aspect_for(brief), gemini_key)

    if img_bytes or vid_bytes:
        attached = " + ".join(x for x in [
            "รูป" if img_bytes else "", "วิดีโอ" if vid_bytes else ""] if x)
        st.caption(f"✅ {attached} จะถูกแนบไปกับโพสต์อัตโนมัติ")

    tabs = st.tabs([f"{PLATFORMS[p]['icon']} {PLATFORMS[p]['name']}" for p in plats])
    for tab, pid in zip(tabs, plats):
        with tab:
            edited = st.text_area(
                "คอนเทนต์",
                value=package.get(pid, ""),
                height=180,
                key=f"copilot_text_{mi}_{pid}",
                label_visibility="collapsed",
            )
            act1, act2 = st.columns(2)
            with act1:
                if st.button("✅ อนุมัติ + โพสต์", key=f"copilot_post_{mi}_{pid}",
                             type="primary", width="stretch"):
                    _do_post(pid, edited, line_token, fb_token, fb_page_id,
                             ig_business_id=ig_business_id,
                             image_bytes=img_bytes,
                             image_name=f"lemed_{mi}.png",
                             video_bytes=vid_bytes,
                             video_name=f"lemed_{mi}.mp4")
            with act2:
                if st.button("📁 ส่งเข้า Catalog (รอจัดคิว)", key=f"copilot_queue_{mi}_{pid}",
                             width="stretch"):
                    # ดึงไฟล์วิดีโอ/รูปภาพจาก session_state ปัจจุบันถ้าไม่ได้ส่งมา
                    cur_vid = vid_bytes or st.session_state.get(f"copilot_vid_{mi}")
                    cur_img = img_bytes or st.session_state.get(f"copilot_img_{mi}")
                    _copilot_send_to_queue(pid, edited, brief,
                                           img_bytes=cur_img,
                                           vid_bytes=cur_vid)

    if st.button("🚀 อนุมัติ + โพสต์ทั้งหมด", key=f"copilot_postall_{mi}",
                 width="stretch"):
        for pid in plats:
            content_i = st.session_state.get(f"copilot_text_{mi}_{pid}") or package.get(pid, "")
            _do_post(pid, content_i, line_token, fb_token, fb_page_id,
                     ig_business_id=ig_business_id, quiet=True,
                     image_bytes=img_bytes, image_name=f"lemed_{mi}.png",
                     video_bytes=vid_bytes, video_name=f"lemed_{mi}.mp4")
        st.success("ส่งคำสั่งโพสต์ครบทุกแพลตฟอร์มแล้ว — ดูผลได้ที่ toast มุมขวาบน")


# ── Integrations ────────────────────────────────────────────────────────────────

_LINE_GUIDE = """
##### ขั้นตอน

**1.** เปิดเว็บ [developers.line.biz](https://developers.line.biz)

**2.** Login ด้วย LINE account

**3.** กดปุ่ม `Create a new provider` (ทำครั้งแรกครั้งเดียว)

**4.** กดปุ่ม `Create a new channel`

**5.** เลือกประเภท `Messaging API`

**6.** กรอกข้อมูล Channel ให้ครบ แล้วกด Create

**7.** เปิด tab `Messaging API`

**8.** เลื่อนลงล่างสุดหา `Channel access token`

**9.** กดปุ่ม `Issue` เพื่อสร้าง token

**10.** Copy token มาวางในช่อง LINE OA Token ด้านบน

---

⚠️ ต้องมี LINE Official Account ก่อน

สมัครฟรีที่ [account.line.biz](https://account.line.biz)
"""

_FB_GUIDE = """
##### ขั้นตอน

**1.** เปิดเว็บ [developers.facebook.com](https://developers.facebook.com)

**2.** Login ด้วย Facebook account

**3.** ที่เมนูบน คลิก `My Apps`

**4.** กดปุ่ม `Create App`

**5.** เลือกประเภท `Business` แล้วกรอกชื่อ app

**6.** ไปที่เมนู `Tools` แล้วเลือก `Graph API Explorer`

**7.** ที่แถบขวา เลือก App ที่เพิ่งสร้าง

**8.** คลิก `Generate Access Token`

**9.** เลือก Facebook Page ที่ต้องการโพสต์

**10.** ติ๊ก permissions ทั้ง 2 ตัว:
- `pages_manage_posts`
- `pages_read_engagement`

**11.** กดปุ่ม `Generate Token` แล้ว Copy token

---

##### วิธีหา Page ID

**1.** เปิด Facebook Page ของคุณ

**2.** คลิกที่แถบ `About`

**3.** เลื่อนลงล่างสุด จะเห็น `Page ID`

---

⚠️ ต้องเป็น Admin ของ Facebook Page
"""

_IG_GUIDE = """
##### ขั้นตอน (ใช้ FB Token เดิม)

**1.** ต้องเชื่อม Instagram กับ Facebook Page ก่อน

**2.** เปิด [Graph API Explorer](https://developers.facebook.com/tools/explorer)

**3.** Method: `GET`

**4.** URL: `{PAGE_ID}?fields=instagram_business_account` (แทน PAGE_ID ด้วย Facebook Page ID)

**5.** กด **ส่ง**

**6.** Response จะมี:
```
"instagram_business_account": {
  "id": "17841xxxxxxxxx"   ← copy เลขนี้
}
```

**7.** วางในช่อง Instagram Business Account ID

---

⚠️ Instagram ต้องเป็น Business/Creator Account
"""


def _render_fb_longlived() -> None:
    """Trade the hour-long Explorer token for one that does not expire.

    Folded away by default: it is a one-time setup step, not something to walk
    past on every visit. Everything it needs is stated before anything is sent —
    the App Secret is a credential, and asking for one without saying where it
    goes is how people learn not to trust a form.
    """
    if not FB_AUTH_AVAILABLE:
        return
    # Stay open while there is something to act on. An expander defaults to
    # closed on every run, so pressing the button folded the page picker away
    # the moment it appeared — the exchange had worked and looked like it had
    # done nothing.
    busy = bool(st.session_state.get("fb_pages")
                or st.session_state.get("fb_exchange_err")
                or st.session_state.get("fb_debug_info"))
    with st.expander("🔁 แลกเป็น token ที่ไม่หมดอายุ (ทำครั้งเดียว)", expanded=busy):
        st.caption(
            "token ที่ copy จาก Graph API Explorer อยู่ได้ราว 1 ชั่วโมง — "
            "นานพอให้ทดสอบผ่าน แล้วไปเงียบตอนโพสต์จริง "
            "แลกครั้งเดียวได้ Page Token ที่ไม่มีวันหมดอายุ"
        )
        st.caption("หา App ID / App Secret ได้ที่ developers.facebook.com → "
                   "App ของคุณ → Settings → Basic (ค่าจะถูกส่งไปที่ Facebook เท่านั้น)")
        c1, c2 = st.columns(2)
        with c1:
            _setting_text("App ID", K_FB_APP, placeholder="เช่น 1234567890")
        with c2:
            _setting_text("App Secret", K_FB_SEC, password=True,
                          placeholder="จาก Settings → Basic")

        app_id, app_secret, token = _s(K_FB_APP), _s(K_FB_SEC), _s(K_FB)
        ready = bool(app_id and app_secret and token)
        if not ready:
            st.caption("ใส่ Page Token ด้านบน + App ID + App Secret ให้ครบก่อน")

        b1, b2 = st.columns(2)
        with b1:
            if st.button("🔁 แลกเป็นแบบถาวร", disabled=not ready,
                         type="primary", width="stretch", key="fb_exchange"):
                with st.spinner("กำลังคุยกับ Facebook..."):
                    user_token, err = facebook_auth.exchange_long_lived(
                        token, app_id, app_secret)
                    pages, perr = ([], err) if err else facebook_auth.list_pages(user_token)
                st.session_state["fb_pages"] = pages
                st.session_state["fb_exchange_err"] = perr
                st.rerun()
        with b2:
            if st.button("🕒 เช็คว่า token หมดอายุเมื่อไหร่", disabled=not ready,
                         width="stretch", key="fb_debug"):
                with st.spinner("กำลังเช็ค..."):
                    info, err = facebook_auth.describe_token(token, app_id, app_secret)
                # Kept in state, not printed here: the button triggers a rerun,
                # the expander folds shut on its own, and anything written inside
                # the click branch disappears with it.
                st.session_state["fb_debug_info"] = info
                st.session_state["fb_debug_err"] = err
                st.rerun()

        if st.session_state.get("fb_exchange_err"):
            st.error(st.session_state["fb_exchange_err"])
        if st.session_state.get("fb_debug_err"):
            st.error(st.session_state["fb_debug_err"])
        if info := st.session_state.get("fb_debug_info"):
            icon = "✅" if info.get("valid") else "❌"
            st.info(f"{icon} token ชนิด {info.get('type', '?')} · "
                    f"{info.get('expires_text', '')}")
            if info.get("scopes"):
                st.caption("สิทธิ์: " + ", ".join(info["scopes"]))

        pages = st.session_state.get("fb_pages") or []
        if pages:
            st.success(f"เจอ {len(pages)} เพจที่คุณเป็นแอดมิน — เลือกเพจที่จะโพสต์")
            names = [f"{p.get('name', '?')} ({p.get('id', '')})" for p in pages]
            choice = st.selectbox("เพจ", names, key="fb_page_choice")
            if st.button("✅ ใช้เพจนี้", type="primary", width="stretch",
                         key="fb_page_apply"):
                page = pages[names.index(choice)]
                token_new, page_id = page.get("access_token", ""), page.get("id", "")
                values = {K_FB: token_new, K_FB_PID: page_id}
                # The page token also answers the Instagram question, which is
                # otherwise a separate trip through Graph API Explorer.
                ig, _ = facebook_auth.instagram_account_for(page_id, token_new)
                if ig:
                    values[K_IG] = ig
                _stage_settings(values)
                st.session_state.pop("fb_pages", None)
                st.session_state["fb_applied"] = page.get("name", "")
                st.rerun()


def _render_saved_settings() -> None:
    """Save what has been typed so a restart does not undo the setup."""
    if not SECRETS_STORE_AVAILABLE:
        return
    st.divider()
    st.markdown("**💾 จำค่าไว้ในเครื่อง**")
    st.caption(f"{secrets_store.describe()} · เก็บเป็นไฟล์ธรรมดาใน "
               "`.streamlit/app_secrets.json` (git ไม่เก็บให้อยู่แล้ว) — "
               "ใครเปิดเครื่องนี้ได้ก็อ่าน token ได้ ถ้าไม่สบายใจให้กดลบ")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("💾 บันทึกค่าที่ใส่ไว้", width="stretch", key="save_settings"):
            ok, msg = secrets_store.save(
                {k: st.session_state.get(k) for k in secrets_store.SAVED_KEYS})
            (st.success if ok else st.error)(msg)
    with c2:
        if st.button("🗑️ ลบค่าที่บันทึกไว้", width="stretch", key="clear_settings"):
            ok, msg = secrets_store.clear()
            (st.success if ok else st.error)(msg)


def _run_connection_test() -> None:
    """Check every configured channel, one line of feedback each."""
    from platform_poster import (test_line_token, test_facebook_token,
                                 test_instagram_account)
    line_token, fb_token = _s(K_LINE), _s(K_FB)
    fb_page_id, ig_id = _s(K_FB_PID), _s(K_IG)

    with st.spinner("กำลังเช็ค..."):
        if line_token:
            ok, m = test_line_token(line_token)
            (st.success if ok else st.error)(m)
        else:
            st.caption("➖ LINE OA: ยังไม่ใส่ token")
        if fb_token and fb_page_id:
            ok, m = test_facebook_token(fb_token, fb_page_id)
            (st.success if ok else st.error)(m)
        else:
            st.caption("➖ Facebook: ยังไม่ใส่ token/Page ID")
        if fb_token and ig_id:
            ok, m = test_instagram_account(ig_id, fb_token)
            (st.success if ok else st.error)(m)
        else:
            st.caption("➖ Instagram: ยังไม่ใส่ IG ID")
        _drive_ready.clear()
        if _drive_ready():
            st.success("Google Drive + YouTube: พร้อม")
        else:
            st.error("Google Drive: ยังไม่ได้ authorize")


def render_integrations_page() -> None:
    """Every posting channel in one place — status first, forms behind tabs.

    These forms used to live in the chat page's sidebar, where four password
    fields and three step-by-step guides sat permanently next to a chat box that
    most sessions never needed them for.
    """
    _apply_pending_settings()   # before any widget on this page exists
    _page_head("การเชื่อมต่อ",
               "ต่อช่องทางที่จะใช้โพสต์ — ใส่ token ครั้งเดียว ใช้ได้ทุกหน้า")
    if applied := st.session_state.pop("fb_applied", ""):
        st.success(f"ใช้เพจ {applied} แล้ว — Page Token, Page ID "
                   "และ Instagram ID (ถ้ามี) ถูกเติมให้อัตโนมัติ")

    status = _connection_status()
    _chips([(f"{name} · {'เชื่อมแล้ว' if ok else 'ยังไม่เชื่อม'}", "ok" if ok else "")
            for name, ok in status])

    tabs = st.tabs(["LINE OA", "Facebook", "Instagram", "TikTok", "Google Drive"])

    with tabs[0]:
        _setting_text("LINE OA Token", K_LINE, password=True,
                      placeholder="Channel Access Token",
                      help="จาก LINE Developers → Messaging API → Channel Access Token")
        if _s(K_LINE):
            st.success("LINE OA พร้อมโพสต์")
        with st.expander("📖 วิธีขอ LINE OA Token"):
            st.markdown(_LINE_GUIDE)

    with tabs[1]:
        _setting_text("Facebook Page Token", K_FB, password=True,
                      placeholder="Page Access Token",
                      help="จาก Meta Developer → Graph API → Page Token")
        if _s(K_FB):
            _setting_text("Facebook Page ID", K_FB_PID, placeholder="เช่น 123456789")
            if _s(K_FB_PID):
                st.success("Facebook พร้อมโพสต์")
        else:
            st.caption("ใส่ Page Token ก่อน แล้วช่อง Page ID จะขึ้นมา")
        _render_fb_longlived()
        with st.expander("📖 วิธีขอ Facebook Page Token"):
            st.markdown(_FB_GUIDE)

    with tabs[2]:
        if not _s(K_FB):
            st.info("Instagram ใช้ token เดียวกับ Facebook — ใส่ Page Token ในแท็บ Facebook ก่อน")
        else:
            _setting_text("Instagram Business Account ID", K_IG,
                          placeholder="เช่น 17841...",
                          help="ID ของ IG Business Account ที่ผูกกับ Facebook Page")
            if _s(K_IG):
                st.success("Instagram พร้อมโพสต์")
        with st.expander("📖 วิธีหา IG Business ID"):
            st.markdown(_IG_GUIDE)

    with tabs[3]:
        if not TIKTOK_AVAILABLE:
            st.info("ยังไม่มีโมดูล tiktok_poster.py ในโปรเจกต์")
        else:
            _setting_text("TikTok Access Token", K_TIKTOK, password=True,
                          placeholder="act....",
                          help="ต้องมี scope video.publish — token อายุสั้น (~24 ชม.)")
            if _s(K_TIKTOK):
                _setting_select(
                    "การมองเห็นโพสต์ TikTok",
                    list(tiktok_poster.PRIVACY_LEVELS.keys()),
                    "tiktok_privacy",
                    format_func=lambda v: tiktok_poster.PRIVACY_LEVELS[v],
                )
                if st.button("ทดสอบ TikTok", width="stretch"):
                    info, m = tiktok_poster.creator_info(_s(K_TIKTOK))
                    (st.success if info else st.error)(m)
                    if info and info.get("creator_nickname"):
                        st.caption(f"บัญชี: {info['creator_nickname']}")
            with st.expander("⚠️ ข้อจำกัด TikTok API"):
                st.markdown(tiktok_poster.describe_limits())
                st.caption("ขอ token ที่ [developers.tiktok.com](https://developers.tiktok.com/)")

    with tabs[4]:
        if _drive_ready():
            st.success("Google Drive + YouTube: พร้อมใช้งาน")
        else:
            st.error("ยังไม่ได้ authorize Google Drive — คิวอนุมัติจะอ่านไฟล์ไม่ได้")
        c1, c2 = st.columns(2)
        with c1:
            st.link_button("📁 เปิดโฟลเดอร์ Drive", DRIVE_FOLDER_URL, width="stretch")
        with c2:
            st.link_button("🎬 เปิด Google Flow", FLOW_PROJECT_URL, width="stretch")

    st.divider()
    if st.button("🔌 เช็คการเชื่อมต่อทั้งหมด", type="primary", width="stretch"):
        _run_connection_test()

    _render_saved_settings()


# ── Settings ────────────────────────────────────────────────────────────────────

def render_settings_page() -> None:
    """AI provider, brand defaults, appearance, POS — the things set once."""
    _page_head("ตั้งค่า", "ตั้งครั้งเดียว ใช้กับทุกหน้า")

    ai_mode = _s(K_AI, "Local Smart")
    _chips([
        (f"AI: {ai_mode}", "on"),
        (f"ธีม: {'มืด' if _theme == 'dark' else 'สว่าง'}", ""),
    ])

    tabs = st.tabs(["AI", "แบรนด์", "หน้าตา", "POS"])

    with tabs[0]:
        mode_now = _setting_radio(
            "โมเดลที่ใช้",
            ["Local Smart", "Gemini API", "Claude API"],
            K_AI, default="Local Smart",
            help="Local Smart ใช้ rule-based logic ทำงานได้ทันที | "
                 "Gemini สร้างรูปได้ด้วย | Claude เน้นคุณภาพงานเขียน",
        )
        if mode_now == "Gemini API":
            _setting_text("Gemini API Key", K_GEMINI, password=True,
                          placeholder="AIza...")
            if _s(K_GEMINI):
                st.success("พร้อมใช้ Gemini — สร้างข้อความ + รูป + อ่านรูป/คลิปได้")
            else:
                st.caption("ขอฟรีที่ [aistudio.google.com/apikey](https://aistudio.google.com/apikey)")
        elif mode_now == "Claude API":
            if not ANTHROPIC_AVAILABLE:
                st.warning("ติดตั้ง anthropic ก่อน:\n`pip install anthropic`")
            _setting_text("Anthropic API Key", K_CLAUDE, password=True,
                          placeholder="sk-ant-...")
            if _s(K_CLAUDE):
                st.success("พร้อมใช้ Claude API — อ่านรูปได้ แต่อ่านคลิปไม่ได้")
        else:
            st.caption("ไม่ต้องใส่ key — ทำงานในเครื่อง ไม่ส่งข้อมูลออก")

    with tabs[1]:
        st.session_state.setdefault("copilot_brand", "LEMED")
        _setting_text("ชื่อแบรนด์", "copilot_brand")
        if COPILOT_AVAILABLE:
            known = content_copilot.product_from_context(
                content_copilot.load_brand_context())
            if known:
                st.success(f"🔒 สินค้าของแบรนด์: **{known}** — คอนเทนต์จะอ้างถึงสินค้านี้เสมอ "
                           "(อ่านจากบริบทแบรนด์ ไม่ใช่เดาจากคำที่พิมพ์)")
        _setting_select(
            "ประเภทธุรกิจ",
            ["auto", "product", "fnb"],
            "copilot_vertical", default="auto",
            format_func=lambda v: {
                "auto": "🔎 ตรวจอัตโนมัติจากคำสั่ง + บริบทแบรนด์",
                "product": "🧴 สินค้า / สกินแคร์ / ความงาม",
                "fnb": "🍜 ร้านอาหาร / คาเฟ่",
            }[v],
            help="กำหนดโทนคอนเทนต์ — ตั้งไว้ถ้าคำสั่งสั้นจนระบบเดาผิด",
        )
        _mandala_badge()

    with tabs[2]:
        st.caption("ธีม")
        tc1, tc2 = st.columns(2)
        with tc1:
            st.button("🌙 มืด" if _theme == "light" else "✓ มืด", width="stretch",
                      type="secondary" if _theme == "light" else "primary",
                      on_click=_set_theme, args=("dark",), key="set_theme_dark")
        with tc2:
            st.button("✓ สว่าง" if _theme == "light" else "☀️ สว่าง", width="stretch",
                      type="primary" if _theme == "light" else "secondary",
                      on_click=_set_theme, args=("light",), key="set_theme_light")
        st.caption("Built with Streamlit + Claude AI")

    with tabs[3]:
        st.caption("Loyverse POS — ใช้กับหน้า 🔌 Connect POS")
        _setting_text("API Token", K_LV, password=True,
                      placeholder="ใส่ token จาก Loyverse Back Office")
        _setting_slider("ดึงข้อมูลย้อนหลัง (วัน)", 7, 90, K_LV_DAY, 30)

    _render_saved_settings()


def render_copilot_page(ai_mode: str, api_key: str, line_token: str = "",
                        fb_token: str = "", fb_page_id: str = "",
                        ig_business_id: str = "") -> None:
    if not COPILOT_AVAILABLE:
        _page_head("แชท AI")
        st.error("ไม่พบ content_copilot.py — ตรวจสอบไฟล์ในโฟลเดอร์โปรเจกต์")
        return

    _key, _provider, _label = _resolve_ai(ai_mode, api_key)
    can_image = _provider == "gemini"
    msgs = st.session_state.setdefault("copilot_msgs", [])

    # ── Empty state ────────────────────────────────────────────────────────
    #
    # The composer is the only thing this page asks anyone to do, so on a blank
    # session it sits directly under the welcome line rather than pinned to the
    # bottom of the window with three rows of chips, an expander and a provider
    # label stacked above it. Streamlit's chat_input is always bottom-docked, so
    # the empty state uses a form instead and hides the docked bar; both paths
    # write to the same `copilot_pending` slot, so submission behaves identically.
    if not msgs:
        st.markdown("<style>[data-testid='stBottom']{display:none !important}</style>",
                    unsafe_allow_html=True)
        _, mid, _r = st.columns([1, 6, 1])
        with mid:
            st.markdown(
                '<div class="rv-hero"><div class="rv-spark">✦</div>'
                '<h2>วันนี้อยากให้ช่วยเรื่องอะไรดีคะ</h2>'
                '<p>พิมพ์บอกแบบพูดคุยได้เลย ไม่ต้องรู้ศัพท์เทคนิค</p></div>',
                unsafe_allow_html=True,
            )
            st.markdown('<p class="rv-ctx">พร้อมช่วยสร้างคอนเทนต์ ตอบลูกค้า '
                        'และวิเคราะห์ธุรกิจ — แนบรูปหรือไฟล์มาให้ดูได้</p>',
                        unsafe_allow_html=True)

            with st.form("copilot_hero", border=False, clear_on_submit=True):
                st.text_area("สิ่งที่อยากให้ AI ช่วย", key="copilot_hero_text",
                             placeholder="พิมพ์สิ่งที่อยากให้ AI ช่วย…",
                             height=104, label_visibility="collapsed")
                st.file_uploader(
                    "แนบรูป ไฟล์ หรือสเปรดชีต (ไม่บังคับ) — รูป/PDF ไม่เกิน 6 MB",
                    type=attachments.UPLOAD_TYPES if ATTACH_AVAILABLE else None,
                    accept_multiple_files=True, key="copilot_hero_files",
                    help="รูปสินค้า · โพสต์คู่แข่ง · สกรีนช็อตยอดขาย · CSV/Excel · PDF",
                    disabled=not ATTACH_AVAILABLE,
                )
                if st.form_submit_button("ส่งให้ AI ช่วย", type="primary",
                                         width="stretch"):
                    text = (st.session_state.get("copilot_hero_text") or "").strip()
                    files = st.session_state.get("copilot_hero_files") or []
                    # A file on its own is a complete request — "ดูรูปนี้ให้หน่อย"
                    # is what the upload already said.
                    if text or files:
                        st.session_state["copilot_pending"] = text
                        st.session_state["copilot_pending_files"] = \
                            attachments.from_uploads(files) if ATTACH_AVAILABLE else []
                        st.rerun()

            with st.container(key="rv_sugg"):
                cols = st.columns(len(_copilot_examples()))
                for i, (label, target) in enumerate(_copilot_examples()):
                    with cols[i]:
                        if st.button(label, key=f"copilot_ex_{i}", width="stretch"):
                            _run_suggestion(label, target)

            can_read = ATTACH_AVAILABLE and _can_read_media(_key, _provider)
            _chips([(_label
                     + (" · สร้างรูปได้" if can_image else "")
                     + (" · อ่านรูป/PDF ได้" if can_read else ""), "on")])
            if ATTACH_AVAILABLE and not can_read:
                st.caption("อ่านรูป/PDF ต้องใส่ key Gemini หรือ Claude ที่ ⚙️ ตั้งค่า — "
                           "ส่วน CSV/Excel/ข้อความ อ่านได้เลยในเครื่อง")

    # ── Conversation ───────────────────────────────────────────────────────
    if msgs:
        head, act = st.columns([4, 1])
        with head:
            _page_head("แชท AI", "ร่างแคปชัน ภาพ และคลิป แล้วส่งเข้าคิวอนุมัติ")
        with act:
            if st.button("🗑️ เริ่มใหม่", key="copilot_clear", width="stretch"):
                st.session_state["copilot_msgs"] = []
                st.rerun()
        _chips([(_label + (" · สร้างรูปได้" if can_image else ""), "on"),
                (f"{len([m for m in msgs if m['role'] == 'user'])} คำสั่งในแชทนี้", "")])

    for mi, m in enumerate(msgs):
        if m["role"] == "user":
            with st.chat_message("user"):
                if m.get("text"):
                    st.markdown(m["text"])
                _render_message_attachments(m.get("files") or [], mi)
        else:
            with st.chat_message("assistant", avatar="🧴"):
                if m.get("error"):
                    st.error(f"ร่างไม่สำเร็จ: {m['error']}")
                else:
                    for note in m.get("notes") or []:
                        st.warning(note)
                    if m.get("read"):
                        with st.expander("📎 สิ่งที่ AI อ่านได้จากไฟล์แนบ", expanded=True):
                            st.markdown(m["read"])
                    if m.get("brief") is not None:
                        _render_copilot_draft(mi, m["brief"], m["package"],
                                              line_token, fb_token, fb_page_id,
                                              ig_business_id,
                                              gemini_key=_key if can_image else "")

    pending = st.session_state.pop("copilot_pending", None)
    pending_files = st.session_state.pop("copilot_pending_files", None) or []
    if msgs:
        # accept_file puts the paperclip inside the composer, so attaching mid-
        # conversation costs no extra chrome. It returns an object, not a string.
        typed = st.chat_input(
            "พิมพ์สิ่งที่อยากให้ AI ช่วย… หรือแนบรูป/ไฟล์",
            accept_file="multiple" if ATTACH_AVAILABLE else False,
            file_type=attachments.UPLOAD_TYPES if ATTACH_AVAILABLE else None,
        )
        if typed:
            if isinstance(typed, str):
                pending = typed
            else:
                pending = (typed.text or "").strip()
                pending_files = attachments.from_uploads(typed.files or [])

    if pending or pending_files:
        msgs.append({"role": "user", "text": pending,
                     "files": [(a.name, a.kind, a.data if a.kind == "image" else None)
                               for a in pending_files]})
        notes: list[str] = []
        read = ""
        if pending_files:
            with st.spinner("กำลังอ่านไฟล์แนบ..."):
                read, notes = attachments.analyze(
                    pending_files, pending or "ช่วยดูไฟล์นี้ให้หน่อย",
                    api_key=_key, provider=_provider)

        # Reading a file is worth showing on its own. Without a usable request
        # there is nothing to draft, so stop at the summary rather than inventing
        # a campaign the user never asked for.
        if not pending and not read:
            msgs.append({"role": "assistant", "brief": None, "package": None,
                         "notes": notes, "read": read})
            st.rerun()

        ask = pending or "ช่วยคิดคอนเทนต์จากไฟล์ที่แนบมา"
        if read:
            ask = f"{ask}\n\n[บริบทจากไฟล์แนบ]\n{read}"

        with st.spinner("กำลังร่างให้..."):
            try:
                brief, package = content_copilot.generate(
                    ask, _key, st.session_state.get("copilot_brand", "LEMED"),
                    provider=_provider,
                    vertical=st.session_state.get("copilot_vertical", "auto"),
                )
                msgs.append({"role": "assistant", "brief": brief, "package": package,
                             "notes": notes, "read": read})
            except Exception as e:  # noqa: BLE001 — surface any failure in-chat
                msgs.append({"role": "assistant", "error": str(e), "notes": notes})
        st.rerun()


# ── AI Chat Inbox ───────────────────────────────────────────────────────────────

def render_ai_inbox_page(ai_mode: str, api_key: str, fb_token: str = "",
                         fb_page_id: str = "", line_token: str = "") -> None:
    _page_head("💬 AI Chat Inbox", "อ่านแชทลูกค้าจาก Facebook Messenger / Instagram DM แล้วให้ AI ช่วยตอบ")

    if not CHAT_INBOX_AVAILABLE:
        st.error("ไม่พบ chat_inbox.py")
        return

    with st.expander("📖 ต้องเปิดสิทธิ์อะไรเพิ่ม (ครั้งแรกครั้งเดียว)"):
        st.markdown("""
##### Facebook Messenger / Instagram DM

**1.** เปิด [Graph API Explorer](https://developers.facebook.com/tools/explorer)

**2.** เพิ่ม permissions:
- `pages_messaging` (อ่าน+ตอบแชท Messenger)
- `instagram_manage_messages` (อ่าน+ตอบ IG DM)

**3.** เลือก "ผู้ใช้หรือเพจ" เป็นเพจของคุณ → กด `Generate Access Token`

**4.** Copy token ใหม่มาวางในช่อง Facebook Page Token (หน้า 🔗 การเชื่อมต่อ)

---

##### LINE OA

LINE ไม่ให้ดึงแชทย้อนหลังผ่าน API — ต้องใช้ **webhook bot**
ดูวิธีตั้งค่าที่หัวข้อ 💚 LINE Auto-Reply Bot ด้านล่างสุด
""")

    # ── Shop profile (AI knowledge) ────────────────────────────────────────────
    st.subheader("🏪 ข้อมูลร้าน (สมองของ AI)")
    prof = st.session_state.setdefault("shop_profile", dict(DEFAULT_PROFILE))
    c1, c2 = st.columns(2)
    with c1:
        prof["shop_name"] = st.text_input("ชื่อร้าน", prof["shop_name"])
        prof["hours"] = st.text_input("เวลาเปิด-ปิด", prof["hours"])
        prof["address"] = st.text_input("ที่อยู่ / การเดินทาง", prof["address"])
    with c2:
        prof["menu"] = st.text_input("เมนูแนะนำ + ราคา", prof["menu"])
        prof["promo"] = st.text_input("โปรโมชันตอนนี้", prof["promo"])
        prof["booking"] = st.text_input("นโยบายจองโต๊ะ", prof["booking"])

    _ai_key = api_key.strip() if (ai_mode == "Claude API" and api_key.strip()) else ""
    st.caption(f"โหมด AI: {'🤖 Claude API (ฉลาด เข้าใจบริบท)' if _ai_key else '⚡ Rule-based (ตอบตามคีย์เวิร์ด — ใส่ Claude API key เพื่ออัปเกรด)'}")

    st.divider()

    # ── Inbox ──────────────────────────────────────────────────────────────────
    plat = st.radio("แพลตฟอร์ม", ["🔵 Facebook Messenger", "🟣 Instagram DM"], horizontal=True)
    platform_key = "messenger" if "Facebook" in plat else "instagram"

    if not fb_token or not fb_page_id:
        st.warning("ใส่ Facebook Page Token + Page ID ในแถบซ้ายก่อน")
        return

    if st.button("🔄 ดึงแชทล่าสุด", type="primary"):
        with st.spinner("กำลังดึงแชท..."):
            convs, msg = fetch_conversations(fb_token, fb_page_id, platform=platform_key)
        if convs is None:
            st.error(msg)
            st.info("ถ้าเจอ error เรื่อง permission — เปิด expander ด้านบนแล้วทำตามขั้นตอนเพิ่มสิทธิ์")
            return
        st.session_state["inbox_convs"] = convs

    convs = st.session_state.get("inbox_convs", [])
    if not convs:
        st.info("กด '🔄 ดึงแชทล่าสุด' เพื่อเริ่ม")
    else:
        waiting = [cv for cv in convs if cv["messages"] and cv["messages"][-1]["from_customer"]]
        st.caption(f"พบ {len(convs)} บทสนทนา — 🔴 รอตอบ {len(waiting)} แชท")

        # ── Auto-reply batch ───────────────────────────────────────────────────
        replied: set = st.session_state.setdefault("auto_replied_ids", set())
        pending = [cv for cv in waiting if cv["messages"][-1]["id"] not in replied]
        if pending:
            if st.button(f"⚡ ให้ AI ตอบ {len(pending)} แชทที่รอ — อัตโนมัติทั้งหมด",
                         type="primary", width="stretch"):
                prog = st.progress(0.0)
                done = 0
                for j, cv in enumerate(pending):
                    reply = generate_ai_reply(cv["messages"], prof, _ai_key)
                    ok, m = send_message(fb_token, fb_page_id, cv["customer_id"], reply)
                    if ok:
                        replied.add(cv["messages"][-1]["id"])
                        done += 1
                    prog.progress((j + 1) / len(pending),
                                  text=f"{cv['customer_name']}: {'✅' if ok else '❌ ' + m}")
                st.success(f"🤖 AI ตอบไปแล้ว {done}/{len(pending)} แชท")

        # ── Conversation list ──────────────────────────────────────────────────
        for i, cv in enumerate(convs):
            is_waiting = cv["messages"] and cv["messages"][-1]["from_customer"]
            badge = "🔴 รอตอบ" if is_waiting else "🟢 ตอบแล้ว"
            with st.expander(f"{badge} — {cv['customer_name']} ({cv['updated'][:16]})",
                             expanded=bool(is_waiting and i < 2)):
                for m in cv["messages"]:
                    if not m["text"]:
                        continue
                    who = "🧑 ลูกค้า" if m["from_customer"] else "🏪 ร้าน"
                    st.markdown(f"**{who}:** {m['text']}")
                st.divider()
                draft_key = f"draft_{cv['conversation_id']}"
                if st.button("🤖 ให้ AI ร่างคำตอบ", key=f"ai_{i}"):
                    with st.spinner("AI กำลังคิด..."):
                        st.session_state[draft_key] = generate_ai_reply(cv["messages"], prof, _ai_key)
                reply_text = st.text_area("คำตอบ", value=st.session_state.get(draft_key, ""),
                                          key=f"txt_{i}", height=100)
                if st.button("📨 ส่งตอบ", key=f"send_{i}", type="primary"):
                    ok, m = send_message(fb_token, fb_page_id, cv["customer_id"], reply_text)
                    (st.success if ok else st.error)(m)

    # ── LINE bot guide ─────────────────────────────────────────────────────────
    st.divider()
    with st.expander("💚 LINE OA Auto-Reply Bot — วิธีตั้งค่า"):
        st.markdown("""
LINE ตอบอัตโนมัติต้องใช้ webhook bot (ไฟล์ `line_ai_bot.py` ในโปรเจกต์นี้ พร้อมใช้แล้ว)

**รันบนเครื่องตัวเอง:**
```bash
pip install fastapi uvicorn
export LINE_CHANNEL_SECRET="จาก LINE Developers → Basic settings"
export LINE_CHANNEL_ACCESS_TOKEN="token ตัวเดียวกับที่ใช้โพสต์"
export ANTHROPIC_API_KEY="sk-ant-..."   # ไม่ใส่ = rule-based
uvicorn line_ai_bot:app --port 8001
```

**เปิด tunnel ให้ LINE เรียกถึง:**
```bash
brew install cloudflared
cloudflared tunnel --url http://localhost:8001
```

**ตั้งค่าใน [LINE Developers Console](https://developers.line.biz/console/):**
1. Messaging API → Webhook URL = `https://<tunnel-url>/webhook`
2. เปิด **Use webhook**
3. ปิด **Auto-reply messages** (ของ LINE เดิม) เพื่อให้ bot ตอบแทน

ทดสอบ: ทักแชทหา OA → AI ตอบกลับทันที 🤖
""")


# ── Sidebar ─────────────────────────────────────────────────────────────────────
#
# Four destinations, a connection summary, and a theme switch. Everything else —
# five password fields, three provider guides, an AI-model radio and a POS token
# — moved onto the Settings and Integrations pages it belongs to. A sidebar that
# scrolls past the fold on a chat page is a settings panel with a chat box
# attached, which is the opposite of what this app is for.

CORE_PAGES = ["🗨️ แชท AI", "✋ คิวอนุมัติ",
              "🔗 การเชื่อมต่อ", "⚙️ ตั้งค่า"]
MORE_PAGES = [
    "🧠 Brain Storm", "🎨 Canva", "📣 Content Studio",
    "💬 AI Inbox", "📊 Dashboard", "📁 Upload Data",
    "🔌 Connect POS", "🧮 ROI Calculator",
]

with st.sidebar:
    _txt_logo = "#F8FAFC" if _theme == "dark" else "#111827"
    # brand orange is a fill colour — as type on the light sidebar it is 2.0:1
    _accent  = "#F59E0B" if _theme == "dark" else "#92400E"
    _txt_ver  = "#8492A6" if _theme == "dark" else "#5B6472"
    st.markdown(f"""
<div style="padding:0.5rem 0 1.25rem 0;">
  <div style="display:flex;align-items:center;gap:10px;">
    <div style="width:32px;height:32px;background:linear-gradient(135deg,#B45309,#F59E0B);border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:14px;flex-shrink:0;">📊</div>
    <div>
      <div style="font-weight:750;font-size:16px;color:{_txt_logo};letter-spacing:-0.01em;line-height:1.2;">REVENUE <span style="color:{_accent};">AI</span></div>
      <div style="font-size:10px;color:{_txt_ver};font-weight:600;letter-spacing:0.1em;text-transform:uppercase;margin-top:2px;">Smart Business Suite</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

    # Mode switch stays the first sidebar widget: anything that triggers a rerun
    # before a keyed widget is instantiated makes Streamlit drop that key, and
    # losing `app_mode` drops the whole app back to shop mode.
    mode = st.radio(
        "โหมดการใช้งาน",
        [MODE_SHOP, MODE_AFFILIATE],
        label_visibility="collapsed",
        key="app_mode",
    )
    st.divider()

    if mode == MODE_AFFILIATE:
        page = st.radio(
            "เมนูแอฟฟิลิเอต",
            affiliate_ui.PAGES if AFFILIATE_AVAILABLE else ["📈 ภาพรวม"],
            label_visibility="collapsed",
            key="aff_menu",
        )
        st.divider()
        if AFFILIATE_AVAILABLE:
            affiliate_ui.sidebar_controls()
    else:
        # Drain a navigation request from elsewhere in the app before the menu
        # widgets exist — after that, Streamlit will not let their keys be set.
        _nav = st.session_state.pop("nav_to", None)
        if _nav:
            if _nav in MORE_PAGES:
                st.session_state["shop_show_all"] = True
            st.session_state["shop_menu"] = _nav

        show_all = st.toggle("🧰 เครื่องมือทั้งหมด", key="shop_show_all",
                             help="เปิดเพื่อใช้เครื่องมือขั้นสูง — งานประจำวันใช้แค่ 4 เมนูบน")
        page = st.radio(
            "เมนู",
            CORE_PAGES + (MORE_PAGES if show_all else []),
            label_visibility="collapsed",
            key="shop_menu",
        )

        # Connection summary — one line instead of five token fields. Says what
        # is ready to post right now, and links to the page that fixes it.
        _conn = _connection_status()
        _n_ok = sum(1 for _, ok in _conn if ok)
        _tone = _accent if _n_ok else ("#8492A6" if _theme == "dark" else "#5B6472")
        st.markdown(
            f'<div class="rv-conn"><span class="rv-conn-l">เชื่อมต่อแล้ว</span>'
            f'<span class="rv-conn-v" style="color:{_tone}">{_n_ok}/{len(_conn)} ช่องทาง</span></div>',
            unsafe_allow_html=True,
        )

    st.divider()
    _tc1, _tc2 = st.columns(2)
    with _tc1:
        st.button("🌙 มืด" if _theme == "light" else "✓ มืด", width="stretch",
                  type="secondary" if _theme == "light" else "primary",
                  on_click=_set_theme, args=("dark",), key="sb_theme_dark")
    with _tc2:
        st.button("✓ สว่าง" if _theme == "light" else "☀️ สว่าง", width="stretch",
                  type="primary" if _theme == "light" else "secondary",
                  on_click=_set_theme, args=("light",), key="sb_theme_light")


# ── Settings read back ──────────────────────────────────────────────────────────
#
# One place where every page gets its credentials, whether or not the form that
# collects them rendered this run.

ai_mode = _s(K_AI, "Local Smart")
api_key = _resolve_api_key(ai_mode)
line_token = _s(K_LINE)
fb_token = _s(K_FB)
fb_page_id = _s(K_FB_PID)
ig_business_id = _s(K_IG)
lv_token = _s(K_LV)
lv_days = st.session_state.get(K_LV_DAY, 30)



# ── Affiliate mode routing ───────────────────────────────────────────────────────

if mode == MODE_AFFILIATE:
    if AFFILIATE_AVAILABLE:
        affiliate_ui.render(page)
    else:
        st.error("โหลดโมดูลแอฟฟิลิเอตไม่ได้ (affiliate_ui.py) — ตรวจสอบไฟล์")
    st.stop()


# ── Page routing (shop owner mode) ───────────────────────────────────────────────

if page == "📁 Upload Data":
    render_csv_upload_page(ai_mode, api_key)
    st.stop()

if page == "🔌 Connect POS":
    render_connect_pos_page(lv_token, lv_days, ai_mode, api_key)
    st.stop()

if page == "🧠 Brain Storm":
    render_brainstorm_page(ai_mode, api_key)
    st.stop()

if page == "🗨️ แชท AI":
    render_copilot_page(ai_mode, api_key, line_token=line_token, fb_token=fb_token, fb_page_id=fb_page_id, ig_business_id=ig_business_id)
    st.stop()

if page == "🎨 Canva":
    render_canva_page()
    st.stop()

if page == "✋ คิวอนุมัติ":
    render_queue_page(line_token=line_token, fb_token=fb_token,
                      fb_page_id=fb_page_id, ig_business_id=ig_business_id)
    st.stop()

if page == "📣 Content Studio":
    render_content_studio_page(ai_mode, api_key, line_token=line_token, fb_token=fb_token, fb_page_id=fb_page_id, ig_business_id=ig_business_id)
    st.stop()

if page == "💬 AI Inbox":
    render_ai_inbox_page(ai_mode, api_key, fb_token=fb_token, fb_page_id=fb_page_id, line_token=line_token)
    st.stop()

if page == "🧮 ROI Calculator":
    render_roi_calculator()
    st.stop()

if page == "🔗 การเชื่อมต่อ":
    render_integrations_page()
    st.stop()

if page == "⚙️ ตั้งค่า":
    render_settings_page()
    st.stop()

# ── Dashboard ───────────────────────────────────────────────────────────────────

_page_head("แดชบอร์ด",
           "Data → Insight → Action | สำหรับร้านอาหาร / คาเฟ่ / บาร์ / ยิม")

# The demo-data selector belongs next to the data it changes, not in a sidebar
# that only grew this control when one particular page happened to be open.
demo_profile = st.radio(
    "ชุดข้อมูลตัวอย่าง",
    ["General Business", "ร้านหมูกระทะ", "ร้านเย็นตาโฟ (ข้อมูลจริง)"],
    horizontal=True, key="demo_profile",
)

if demo_profile == "ร้านเย็นตาโฟ (ข้อมูลจริง)":
    st.info("กำลังแสดงข้อมูลจริงของลูกค้าร้านเย็นตาโฟจากไฟล์ Excel")
    render_yentafo_dashboard(load_yentafo_aggregates(YENTAFO_DIR))
    st.stop()
elif demo_profile == "ร้านหมูกระทะ":
    df = generate_mookrata_data()
    st.info("กำลังแสดงข้อมูลจำลองร้านหมูกระทะ")
else:
    df = load_data()

# Date + branch filter
min_date = df["order_time"].min().date()
max_date = df["order_time"].max().date()
left, right = st.columns([2, 1])
with left:
    selected_dates = st.date_input(
        "ช่วงข้อมูล",
        value=(max_date - dt.timedelta(days=30), max_date),
        min_value=min_date, max_value=max_date,
    )
with right:
    branch_filter = st.multiselect(
        "เลือกสาขา",
        options=sorted(df["branch"].unique()),
        default=sorted(df["branch"].unique()),
    )

if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
    start_date, end_date = selected_dates
else:
    start_date, end_date = max_date - dt.timedelta(days=30), max_date

filtered = df[
    (df["order_time"].dt.date >= start_date) &
    (df["order_time"].dt.date <= end_date) &
    (df["branch"].isin(branch_filter))
].copy()

if filtered.empty:
    st.warning("ไม่พบข้อมูลในช่วงที่เลือก")
    st.stop()

# KPI row
sales = filtered["net_sales"].sum()
margin = filtered["margin"].sum()
aov = filtered["net_sales"].mean()
repeat_rate = (filtered["customer_segment"] != "new").mean() if "customer_segment" in filtered.columns else 0

k1, k2, k3, k4 = st.columns(4)
k1.metric("Revenue", f"฿{sales:,.0f}")
k2.metric("Margin", f"฿{margin:,.0f}")
k3.metric("AOV", f"฿{aov:,.0f}")
k4.metric("Repeat Rate", f"{repeat_rate:.1%}")

forecast_df = get_sales_forecast(filtered)
if not forecast_df.empty:
    next_7d = forecast_df[forecast_df["type"] == "Forecast"]["net_sales"].sum()
    st.info(f"💡 **AI Forecast:** คาดการณ์ยอดขาย 7 วันข้างหน้า: **฿{next_7d:,.0f}**")

if "service_type" in filtered.columns:
    buffet_share = (filtered["service_type"] == "buffet").mean()
    st.caption(f"Service Mix — Buffet: {buffet_share:.1%} | À la carte: {1 - buffet_share:.1%}")

# 4 tabs
tab1, tab2, tab3, tab4 = st.tabs(["Executive Dashboard", "Customer Intelligence", "Real-time Marketing", "Branch & Staff"])

with tab1:
    daily = (
        filtered.assign(order_date=filtered["order_time"].dt.date)
        .groupby("order_date", as_index=False)["net_sales"].sum()
    )
    
    # Sales Forecast
    st.subheader("ยอดขายและการพยากรณ์ (Sales Forecast)")
    forecast_df = get_sales_forecast(filtered)
    if not forecast_df.empty:
        fig = px.line(
            forecast_df, x="date", y="net_sales", color="type",
            line_dash="type", markers=True,
            title="Actual Sales vs 7-Day Forecast",
            color_discrete_map={"Actual": "#3B82F6", "Forecast": "#F59E0B"}
        )
        _chart(fig)
    else:
        _chart(px.line(daily, x="order_date", y="net_sales", title="ยอดขายรายวัน", markers=True))

    top_items = (
        filtered.groupby("item", as_index=False)["margin"].sum()
        .sort_values("margin", ascending=False).head(5)
    ) if "item" in filtered.columns else pd.DataFrame()
    if not top_items.empty:
        _chart(px.bar(top_items, x="item", y="margin", title="Top 5 Items by Margin"))

    if "service_type" in filtered.columns:
        mix = filtered.groupby("service_type", as_index=False)["net_sales"].sum()
        _chart(px.bar(mix, x="service_type", y="net_sales", title="ยอดขายตามประเภทบริการ"))

with tab2:
    # Compute RFM for the filtered dataset
    rfm_data = compute_rfm(filtered)
    if not rfm_data.empty:
        filtered = label_transactions(filtered, rfm_data)
    _render_rfm_tab(filtered, rfm_data)

    st.divider()
    st.subheader(f"AI Insights ({ai_mode})")
    with st.spinner("กำลังวิเคราะห์..."):
        for insight in get_ai_insights(filtered, ai_mode, api_key):
            st.success(insight)

with tab3:
    hourly_df = (
        filtered.assign(order_hour=filtered["order_time"].dt.hour)
        .groupby("order_hour", as_index=False)["net_sales"].sum()
    )
    _chart(px.area(hourly_df, x="order_hour", y="net_sales", title="Opportunity by Hour"))

    st.subheader("Recommended Campaign & Content")
    for line in content_suggestions(filtered):
        st.info(line)

with tab4:
    by_branch = filtered.groupby("branch", as_index=False).agg(
        revenue=("net_sales", "sum"),
        margin=("margin", "sum"),
        transactions=("order_id", "count"),
    )
    st.dataframe(by_branch)

    if "staff" in filtered.columns:
        by_staff = (
            filtered.groupby("staff", as_index=False).agg(
                revenue=("net_sales", "sum"),
                margin=("margin", "sum"),
                transactions=("order_id", "count"),
            ).sort_values("revenue", ascending=False)
        )
        st.dataframe(by_staff)

st.divider()
dl_col, info_col = st.columns([1, 2])
with dl_col:
    st.download_button(
        label="📥 Download Report (.xlsx)",
        data=generate_excel_report(filtered),
        file_name=f"ai_revenue_{dt.datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )
with info_col:
    st.caption("รายงานรวม 7 sheet: KPI Summary, Daily Sales, Top Items, Branch Performance, Customer Segments, Hourly Revenue, AI Insights")

