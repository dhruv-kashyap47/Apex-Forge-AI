"""Runtime security checks and optional access gate for ApexForge."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import streamlit as st


@dataclass(frozen=True)
class SecurityFinding:
    severity: str
    title: str
    detail: str
    remediation: str


def _is_placeholder(value: str | None) -> bool:
    if not value:
        return True
    lowered = value.strip().lower()
    return lowered in {
        "change_this_to_a_random_secret_key_in_production",
        "change-me",
        "changeme",
        "password",
        "secret",
        "your-secret-key",
        "replace-me",
        "replace_with_a_long_random_value",
        "apexforge_secret_2026",
    }


def is_production() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() == "production"


def collect_findings() -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    secret_key = os.getenv("APP_SECRET_KEY")
    app_access_code = os.getenv("APP_ACCESS_CODE")
    postgres_password = os.getenv("POSTGRES_PASSWORD")

    if is_production():
        if _is_placeholder(secret_key) or len(secret_key or "") < 32:
            findings.append(SecurityFinding(
                "critical",
                "Weak APP_SECRET_KEY",
                "Production mode is using a missing or weak secret key.",
                "Set APP_SECRET_KEY to a random value of at least 32 characters.",
            ))
        if _is_placeholder(postgres_password) or len(postgres_password or "") < 16:
            findings.append(SecurityFinding(
                "critical",
                "Weak POSTGRES_PASSWORD",
                "Production mode should not use a default database password.",
                "Set POSTGRES_PASSWORD to a unique long password in the deployment environment.",
            ))
        if not app_access_code:
            findings.append(SecurityFinding(
                "warning",
                "No access code configured",
                "The UI is not protected by an unlock screen.",
                "Set APP_ACCESS_CODE to protect the deployment with a simple gate.",
            ))
    else:
        if _is_placeholder(secret_key):
            findings.append(SecurityFinding(
                "warning",
                "Default APP_SECRET_KEY",
                "Development mode is still using the template secret key.",
                "Set APP_SECRET_KEY before any shared or public deployment.",
            ))
        if _is_placeholder(postgres_password):
            findings.append(SecurityFinding(
                "warning",
                "Default POSTGRES_PASSWORD",
                "The template database password is still in place.",
                "Replace it before using Docker in a shared environment.",
            ))

    streamlit_config = Path(".streamlit/config.toml")
    if streamlit_config.exists():
        content = streamlit_config.read_text(encoding="utf-8").lower()
        if "enablecors = false" in content and "enablexsrfprotection = true" in content:
            findings.append(SecurityFinding(
                "critical",
                "Insecure Streamlit CORS/XSRF combination",
                "CORS was disabled while XSRF protection remained enabled.",
                "Keep enableCORS=true when enableXsrfProtection=true.",
            ))

    return findings


def render_security_sidebar() -> None:
    findings = collect_findings()
    critical = [f for f in findings if f.severity == "critical"]
    warnings = [f for f in findings if f.severity == "warning"]

    st.sidebar.markdown("### Security")
    if critical:
        st.sidebar.error(f"{len(critical)} critical issue(s) detected")
    elif warnings:
        st.sidebar.warning(f"{len(warnings)} warning(s) detected")
    else:
        st.sidebar.success("Security checks passed")

    if findings:
        with st.sidebar.expander("View checks", expanded=False):
            for finding in findings:
                label = finding.severity.capitalize()
                st.markdown(f"**{label}:** {finding.title}")
                st.caption(finding.detail)
                st.caption(f"Fix: {finding.remediation}")


def render_access_gate() -> bool:
    access_code = os.getenv("APP_ACCESS_CODE", "").strip()
    if not access_code:
        return True
    if st.session_state.get("_apexforge_unlocked"):
        return True

    st.markdown(
        """
        <div style="max-width:520px;margin:10vh auto;padding:2rem;border:1px solid #1e2e52;
                    border-radius:18px;background:#0f1628">
          <h2 style="margin:0 0 0.5rem;color:#f1f5f9">Access required</h2>
          <p style="margin:0;color:#94a3b8">
            This deployment is protected by an unlock code.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    entered = st.text_input("Unlock code", type="password", key="_apexforge_access_code")
    if st.button("Unlock", type="primary"):
        if secrets.compare_digest(entered.strip(), access_code):
            st.session_state["_apexforge_unlocked"] = True
            st.rerun()
        st.error("Incorrect access code.")
    return False


def fail_if_critical(findings: Iterable[SecurityFinding]) -> None:
    critical = [f for f in findings if f.severity == "critical"]
    if critical:
        st.error("Deployment security checks failed.")
        for finding in critical:
            st.markdown(f"- {finding.title}: {finding.detail}")
        st.stop()
