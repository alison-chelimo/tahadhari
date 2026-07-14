import json
import os

import httpx
import streamlit as st


st.set_page_config(page_title="Tahadhari Demo Dashboard", layout="wide")
st.title("Tahadhari Delivery and Corridor Demo")

base_url_default = os.getenv("TAHADHARI_API_BASE_URL", "http://localhost:8000")
service_key_default = os.getenv("SERVICE_API_KEY", "")

base_url = st.sidebar.text_input("API Base URL", value=base_url_default).rstrip("/")
service_key = st.sidebar.text_input("Service API Key", value=service_key_default, type="password")
headers = {"X-API-Key": service_key} if service_key else {}


def api_request(method: str, path: str, payload: dict | None = None, params: dict | None = None):
    url = f"{base_url}{path}"
    with httpx.Client(timeout=20.0) as client:
        response = client.request(method, url, json=payload, params=params, headers=headers)
    return response


col_a, col_b = st.columns(2)

with col_a:
    st.subheader("1) Ingest Alert")
    with st.form("ingest_form"):
        source = st.text_input("Source", value="KMD_test")
        geography_type = st.selectbox("Geography Type", options=["ward", "corridor"])
        geography_ref = st.text_input("Geography Ref", value="Kisumu_Central")
        rainfall_mm = st.number_input("Rainfall (mm)", min_value=0.0, value=65.0, step=1.0)
        raw_payload_text = st.text_area("Raw Payload JSON", value='{"forecast_window": "next_24h", "confidence": "high"}')
        submitted = st.form_submit_button("Ingest")
        if submitted:
            try:
                raw_payload = json.loads(raw_payload_text) if raw_payload_text.strip() else None
                payload = {
                    "source": source,
                    "geography_type": geography_type,
                    "geography_ref": geography_ref,
                    "rainfall_mm": rainfall_mm,
                    "raw_payload": raw_payload,
                }
                resp = api_request("POST", "/alerts/ingest", payload=payload)
                st.write(resp.status_code, resp.json())
            except Exception as exc:
                st.error(str(exc))

with col_b:
    st.subheader("2) Corridor Prediction + Maps")
    alert_id_for_predict = st.number_input("Corridor Alert ID", min_value=1, value=1, step=1)
    if st.button("Run Flood Prediction"):
        resp = api_request("POST", f"/alerts/predict/{int(alert_id_for_predict)}")
        st.write(resp.status_code, resp.json())

    if st.button("Load Corridor Maps"):
        resp = api_request("GET", f"/maps/alerts/{int(alert_id_for_predict)}/corridor")
        st.write(resp.status_code)
        data = resp.json()
        st.json(data)
        for item in data.get("maps", []):
            st.markdown(f"Segment: {item['segment_name']} ({item['risk_level']})")
            st.image(item["map_url"], caption=item["segment_name"])

st.divider()

col_c, col_d = st.columns(2)

with col_c:
    st.subheader("3) Create Message Record")
    with st.form("message_form"):
        profile_id = st.number_input("Profile ID", min_value=1, value=1, step=1)
        alert_id = st.number_input("Alert ID", min_value=1, value=1, step=1)
        template_id_text = st.text_input("Template ID (optional)", value="")
        flood_prediction_id_text = st.text_input("Flood Prediction ID (optional)", value="")
        channel = st.selectbox("Channel", options=["whatsapp", "sms"])
        final_text = st.text_area("Final Message Text", value="Heavy rainfall expected. Take precautions.")
        create_msg = st.form_submit_button("Create Message")

        if create_msg:
            payload = {
                "profile_id": int(profile_id),
                "alert_id": int(alert_id),
                "final_text": final_text,
                "channel": channel,
            }
            if template_id_text.strip():
                payload["template_id"] = int(template_id_text.strip())
            if flood_prediction_id_text.strip():
                payload["flood_prediction_id"] = int(flood_prediction_id_text.strip())

            resp = api_request("POST", "/messages/", payload=payload)
            st.write(resp.status_code, resp.json())

with col_d:
    st.subheader("4) Send Delivery")
    with st.form("delivery_form"):
        message_id = st.number_input("Message ID", min_value=1, value=1, step=1)
        force_channel = st.selectbox("Force Channel", options=["", "whatsapp", "sms"])
        media_url = st.text_input("Media URL (optional)", value="")
        send_now = st.form_submit_button("Send Message")

        if send_now:
            payload = {}
            if force_channel:
                payload["force_channel"] = force_channel
            if media_url.strip():
                payload["media_url"] = media_url.strip()
            resp = api_request("POST", f"/delivery/messages/{int(message_id)}/send", payload=payload)
            st.write(resp.status_code, resp.json())
