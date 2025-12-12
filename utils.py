#!/usr/bin/env python3
import streamlit as st

def circular_gauge(score: float, label="Quality Score", size: int = 180):
    """
    Renders a circular gauge with visible label.
    - score: 0..100
    - label: text shown beneath percentage
    - size: pixel diameter of outer circle
    """
    pct = min(max(score or 0.0, 0.0), 100.0)
    # color thresholds
    if pct >= 80:
        color = "#4caf50"  # green
    elif pct >= 50:
        color = "#f9a825"  # amber
    else:
        color = "#e53935"  # red

    inner = int(size * 0.78)
    html = f"""
    <div style="display:flex; justify-content:center; margin:14px 0 22px 0;">
      <div style="width:{size}px; height:{size}px; border-radius:50%;
                  background: conic-gradient({color} {pct*3.6}deg, #e6e6e6 0deg);
                  display:flex; align-items:center; justify-content:center;
                  box-shadow: 0 6px 18px rgba(0,0,0,0.08);">
        <div style="width:{inner}px; height:{inner}px; border-radius:50%; background: #ffffff;
                    display:flex; flex-direction:column; align-items:center; justify-content:center;">
          <div style="font-size:{int(inner*0.28)}px; font-weight:700; color:#222;">{pct:.1f}%</div>
          <div style="font-size:14px; color:#666; margin-top:6px;">{label}</div>
        </div>
      </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)
