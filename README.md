# Agentic-AI: Responsible HR Assistant Sandbox

This repository contains an experimental sandbox for building production-ready, Responsible Agentic AI systems. It demonstrates how to enforce security, governance, and access controls over an LLM-powered agent using a modular architecture.

## Features

*   **Role-Based Access Control (RBAC):** Documents in the vector store are pre-filtered based on the user's ACL level before being passed to the LLM.
*   **Human-in-the-Loop (HITL) Queue:** High-risk actions (like modifying payroll) are intercepted and require explicit human approval via the UI before execution.
*   **Policy Engine & Autonomy Tiers:** Queries are classified into AUTONOMOUS (read-only), SUPERVISED (self-service write), or REQUIRES_HITL (high-risk write) tiers.
*   **Data Poisoning Prevention:** Implements SHA-256 hash checks on all documents to detect and block tampered context from being passed to the LLM.
*   **Prompt Injection Filters:** Pre-filters scan for jailbreaks and Unicode smuggling; post-filters scan retrieved documents for indirect injections.
*   **Real-time Observability:** A Server-Sent Events (SSE) stream broadcasts every pipeline step (ACL resolution, embedding, generation) to the UI in real-time.
*   **Audit Trail:** An immutable audit logger records all actions, access denials, and HITL decisions.

## Architecture

*   **Backend:** Python 3.9+, FastAPI, Uvicorn, ChromaDB (in-memory)
*   **LLM & Embeddings:** Google Gemini (`gemini-3.1-flash-lite`, `gemini-embedding-001`) via the `google-genai` SDK.
*   **Frontend:** Vanilla HTML/JS/CSS (served statically by FastAPI)

*For more details, refer to the article on Towards Data Science — [From Prototype to Production: The Architecture Behind Secure & Governed AI Agents](https://towardsdatascience.com/from-prototype-to-production-the-architecture-behind-secure-governed-ai-agents/)*

## Setup Instructions

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/Proxy-Pointer/Agentic-AI.git
    cd Agentic-AI
    ```

2.  **Create a Virtual Environment:**
    ```bash
    python -m venv venv
    ```
    Activate it:
    *   Windows: `.\venv\Scripts\activate`
    *   macOS/Linux: `source venv/bin/activate`

3.  **Install Dependencies:**
    ```bash
    pip install -r backend/requirements.txt
    ```

4.  **Configure Environment Variables:**
    Copy the example environment file and add your Google Gemini API Key:
    ```bash
    cp .env.example .env
    ```
    Open `.env` and set `GOOGLE_API_KEY=your_key_here`. Get a free key at [Google AI Studio](https://aistudio.google.com/).

5.  **Run the Server:**
    ```bash
    python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
    ```

6.  **Access the UI:**
    Open your browser and navigate to: [http://localhost:8000/app](http://localhost:8000/app)

## Exploration Guide

Once the UI is running, use the **Quick Test Cases** buttons at the bottom of the screen to explore different RAI principles:

*   **GOV-01 & GOV-03 (Governance):** Test how the agent handles simple read requests vs. high-risk write requests that trigger the HITL approval flow.
*   **ACL-03 (Access Control):** Attempt to access confidential PII records as a standard employee (Alice) vs. an Administrator.
*   **INJ-01 & INJ-02 (AI Safety):** Attempt direct prompt injections (jailbreaks) and indirect prompt injections (payloads hidden in retrieved documents).
*   **POI-01 (Data Integrity):** Toggle the "Tamper" switch on a document to simulate data poisoning and watch the integrity checker block it.
*   **AUD-01 & AUD-02 (Auditability):** View the real-time execution trace and generate compliance summary reports.
