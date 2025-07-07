import sys
import io
import re
from datetime import datetime, date, time, timedelta
import urllib.parse

import numpy as np
import streamlit as st
from PIL import Image
import easyocr
import dateparser
from streamlit_paste_button import paste_image_button
from icalendar import Calendar, Event

# — Authentication —
PASSWORD = "vibing"
user_pass = st.sidebar.text_input("Enter password to access the app:", type="password")
if user_pass != PASSWORD:
    st.warning("🔒 Please enter the correct password to continue.")
    st.stop()

st.write("Python executable:", sys.executable)
st.title("📅 Vibe Scheduler — Extract, Edit & Add to Google Calendar")

# --- Helper functions ---

def clean_title(raw_title):
    title = raw_title.strip(" .,:;-_\n\t")
    if len(title) > 1 and title[0].isalpha() and title[1] == " ":
        title = title[2:].strip()
    return title


def find_dates(text):
    pattern = (
        r"\b(?:\d{1,2}\s)?(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b"
        r"|\b\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}\b"
    )
    results = []
    for m in re.finditer(pattern, text, flags=re.IGNORECASE):
        dt = dateparser.parse(m.group(), settings={"PREFER_DATES_FROM": "future"})
        if dt:
            results.append({"date": dt.date(), "start": m.start(), "end": m.end()})
    return results


def find_time_ranges_near(text, pos, window=50):
    pattern = (
        r"(\d{1,2}:\d{2}(?:\s*[APMapm\.]+)?\s*[-–]\s*\d{1,2}:\d{2}(?:\s*[APMapm\.]+)?)"
    )
    snippet = text[max(0, pos-window): pos+window]
    m = re.search(pattern, snippet)
    if not m:
        return None, None
    start_str, end_str = [s.strip() for s in re.split(r"[-–]", m.group(), maxsplit=1)]
    dt1 = dateparser.parse(start_str)
    dt2 = dateparser.parse(end_str)
    return (dt1.time() if dt1 else None), (dt2.time() if dt2 else None)


def extract_events(text):
    events = []
    for entry in find_dates(text):
        d, s, e = entry["date"], entry["start"], entry["end"]
        start_time, end_time = find_time_ranges_near(text, s)
        raw = text[max(0, s-30): e+20]
        title = clean_title(raw) or "No title found"
        if not start_time:
            start_time = time(9, 0)
        if not end_time:
            end_time = (datetime.combine(date.today(), start_time) + timedelta(hours=1)).time()
        events.append({"title": title, "date": d, "start_time": start_time, "end_time": end_time})
    return events

# --- Initialize OCR reader once ---
reader = easyocr.Reader(['en'], gpu=False)

# --- Main App Flow ---
# 1. Paste image
paste_res = paste_image_button("📋 Paste image")
data = getattr(paste_res, 'image_data', None)
if data is None:
    st.info("📋 Copy a screenshot, then press Ctrl+V to paste an image here.")
    st.stop()

# 2. Convert paste data to PIL.Image
if isinstance(data, (bytes, bytearray)):
    image = Image.open(io.BytesIO(data))
elif isinstance(data, np.ndarray):
    image = Image.fromarray(data)
elif isinstance(data, Image.Image):
    image = data
else:
    st.error(f"Unsupported paste data type: {type(data)}")
    st.stop()

# 3. Display image
st.image(image, caption="📋 Pasted Image", use_container_width=True)

# 4. OCR with EasyOCR
result = reader.readtext(np.array(image))
raw_text = "\n".join([item[1] for item in result])
st.subheader("📝 Extracted Text")
st.write(raw_text)

# 5. Extract events
events = extract_events(raw_text)
st.subheader("🗓️ Extracted Events (editable)")

if not events:
    st.write("No events found.")
else:
    for i, ev in enumerate(events):
        title = st.text_input(f"Event {i+1} Title:", value=ev['title'], key=f"title_{i}")
        date_val = st.date_input(f"Event {i+1} Date:", value=ev['date'], key=f"date_{i}")
        start_val = st.time_input("Start Time:", value=ev['start_time'], key=f"start_{i}")
        end_val = st.time_input("End Time:", value=ev['end_time'], key=f"end_{i}")

        # Build ICS
        cal = Calendar()
        e = Event()
        e.add('summary', title)
        dtstart = datetime.combine(date_val, start_val)
        dtend = datetime.combine(date_val, end_val)
        e.add('dtstart', dtstart)
        e.add('dtend', dtend)
        cal.add_component(e)
        ics_bytes = cal.to_ical()

        # Download ICS
        st.download_button(
            label=f"⬇️ Download ICS for Event {i+1}",
            data=ics_bytes,
            file_name=f"{title}.ics",
            mime="text/calendar",
            key=f"dl_{i}"
        )

        # Add to Google Calendar link
        dtfmt = "%Y%m%dT%H%M%S"
        start_str = dtstart.strftime(dtfmt)
        end_str = dtend.strftime(dtfmt)
        params = {
            'action': 'TEMPLATE',
            'text': title,
            'dates': f"{start_str}/{end_str}",
        }
        url = "https://calendar.google.com/calendar/render?" + urllib.parse.urlencode(params)
        st.markdown(f"[➕ Add to Google Calendar]({url})", unsafe_allow_html=True)
