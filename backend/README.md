# Green-Agentic Backend API 

This is the complete, production-ready backend for the Green-Agentic Document Intelligence Platform. It is designed to run 100% locally on a laptop with *no* Docker or database server required.

It uses:
- **FastAPI** for the API
- **LangGraph** for the agentic "brain" (the Orchestrator)
- **unstructured** for "visual" document triage (PDFs, tables, etc.)
- **SQLite** for metadata (file-based)
- **ChromaDB** for vector storage (file-based)
- A **Hybrid MoE** model stack (local + cloud) for green efficiency.

This backend is designed to fulfill your goal of reducing CO2e by intelligently routing tasks to the most efficient model, rather than using one powerful model for everything.

## How to Run This

1.  **Install Ollama:**
    * Download and install Ollama from [ollama.com](https://ollama.com/).
    * Run the Ollama application in the background.

2.  **Pull the Free Models:**
    * Open your terminal and run:
    ```bash
    ollama pull gemma:2b   # Our "Medium" model
    ```

3.  **Install System Dependencies (for `unstructured`):**
    * This is for visual document analysis.
    * **On Mac:** `brew install tesseract poppler`
    * **On Ubuntu/Linux:** `sudo apt-get install tesseract-ocr poppler-utils`
    * **On Windows:** You must install [Tesseract](https://github.com/tesseract-ocr/tessdoc) and [Poppler for Windows](https://github.com/oschwartz10612/poppler-windows/releases/) and add them to your system's PATH.

4.  **Install Python Dependencies:**
    * Create a virtual environment: `python -m venv .venv`
    * Activate it: `source .venv/bin/activate` (or `.venv\Scripts\activate` on Windows)
    * Install requirements from the `requirements.txt` file:
        ```bash
        pip install -r requirements.txt
        ```

5.  **Set Up Environment:**
    * Copy the example `.env` file: `cp .env.example .env`
    * **CRITICAL:** Open the `.env` file and add your **`GROQ_API_KEY`** (from Groq).

6.  **Run the FastAPI Server:**
    * From within the `backend/` directory:
    ```bash
    uvicorn src.api.main:app --reload --port 8000
    ```
    * Your API is now running at `http://127.0.0.1:8000`.
    * You can see the auto-generated documentation at `http://127.0.0.1:8000/docs`.