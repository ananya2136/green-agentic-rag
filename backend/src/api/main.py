from fastapi import FastAPI, UploadFile, HTTPException, Request, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager
import logging
import uuid
import os
import shutil
from typing import Dict, Any, List
from datetime import timedelta

from src.api.schemas import (
    SummaryResponse, CarbonData, RagQueryRequest, 
    RagQueryResponse, JobStatus, SummarizeJobResponse,
    UserRegister, UserLogin, Token, UserResponse
)
from src.core.orchestrator import agentic_graph, JOB_STATUSES
from src.core.config import settings
from src.agents import models
from src.memory import storage
from src.api import auth

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# Create a directory to store temporary uploaded files
UPLOAD_DIR = "temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# --- Startup/Shutdown Events ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    This function runs on application startup.
    1. It cleans up old databases/files from previous runs.
    2. It loads all the local AI models (Light, Embedding, Checker) into memory.
    3. It initializes the file-based databases.
    This ensures our API is instantly ready to process requests.
    """
    
    # 1. Clean up old files *before* starting
    log.info("API Startup: Checking local databases...")
    
    # NOTE: We disabled auto-cleanup to allow Persistent History.
    # To reset, manually delete 'local_db' and 'agentic_db.sqlite'.
    
    # if os.path.exists(settings.VECTOR_DB_PATH):
    #     try:
    #         shutil.rmtree(settings.VECTOR_DB_PATH)
    #         log.info(f"Removed old vector DB at {settings.VECTOR_DB_PATH}")
    #     except Exception as e:
    #         log.warning(f"Could not remove vector DB: {e}")
            
    # if os.path.exists("agentic_db.sqlite"):
    #     try:
    #         os.remove("agentic_db.sqlite")
    #         log.info("Removed old metadata DB (agentic_db.sqlite)")
    #     except Exception as e:
    #         log.warning(f"Could not remove metadata DB: {e}")

    # Clear out any old temporary file uploads
    if os.path.exists(UPLOAD_DIR):
        try:
            shutil.rmtree(UPLOAD_DIR)
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            log.info("Cleared temp_uploads directory.")
        except Exception as e:
            log.warning(f"Could not clear temp_uploads: {e}")
            
    log.info("Startup checks complete.")
    
    # 2. Load all local AI models into memory
    models.load_all_models()
    
    # 3. --- THIS IS A FIX ---
    # Initialize the databases (SQLite and ChromaDB)
    # This was missing, which caused your RAG queries to fail.
    storage.init_database()
    
    # Once startup is done, 'yield' to let the app run
    yield
    
    # (Code here would run on shutdown)
    log.info("API Shutdown.")


# --- Create FastAPI App ---
app = FastAPI(
    title="Green Agentic System - Orchestrator API",
    description="Production-Ready E2E Backend (No-Docker Laptop Version)",
    version="4.0.0-local",
    lifespan=lifespan
)

# --- CORS Middleware ---
# IMPORTANT: For production, restrict origins to specific domains
# For local development, we allow all origins to prevent CORS issues
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for local development
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, PUT, DELETE, OPTIONS, etc.)
    allow_headers=["*"],  # Allow all headers
)

# --- Helper Function ---
async def save_upload_file(file: UploadFile) -> (str, str, str):
    """
    Saves the uploaded file to a temporary directory with a unique ID.
    Returns the file path, a new job_id, and a new document_id.
    """
    job_id = str(uuid.uuid4())
    document_id = job_id 
    file_path = os.path.join(UPLOAD_DIR, f"{job_id}_{file.filename}")
    
    try:
        with open(file_path, "wb") as buffer:
            contents = await file.read()
            buffer.write(contents)
    except Exception as e:
        log.error(f"Error saving file: {e}")
        raise HTTPException(status_code=500, detail="Error saving uploaded file.")
    
    return file_path, job_id, document_id

# --- Background Task Runner ---
def run_orchestrator_job(file_path: str, file_type: str, job_id: str, document_id: str, mode: str):
    """
    This is the main background task that runs the *entire* agentic pipeline.
    """
    try:
        # 1. Set the initial job status
        JOB_STATUSES[job_id] = {"status": "processing", "progress": 5.0, "message": "Job initialized. Preparing agentic graph..."}
        
        # 2. This is the initial "state" we pass to the LangGraph orchestrator
        initial_state = {
            "file_path": file_path,
            "file_type": file_type,
            "job_id": job_id,
            "document_id": document_id,
            "job_mode": mode,
            "final_summary": "",
            "total_chunks": 0,
            "chunks_escalated": 0,
            "carbon_report": {},
            # This is new: a dictionary to track model usage for carbon calculation
            "model_usage_chars": {"light": 0, "medium": 0, "large": 0},
        }
        
        # 3. This is the blocking call that runs the whole LangGraph agent
        log.info(f"Job {job_id}: Invoking Agentic Graph...")
        final_state = agentic_graph.invoke(initial_state)
        
        # 4. Job is done. Store the final results.
        log.info(f"Job {job_id} completed successfully.")
        
        final_carbon_data = {
            **final_state["carbon_report"], 
        }
        
        JOB_STATUSES[job_id] = {
            "status": "complete",
            "progress": 100.0,
            "message": "Job complete. Results are ready.",
            "result": {
                "document_id": document_id,
                "filename": os.path.basename(file_path).split('_', 1)[-1],
                "final_summary": final_state["final_summary"],
                "carbon_data": final_carbon_data,
                "job_id": job_id
            }
        }
        
        # 5. Clean up the uploaded file
        os.remove(file_path)

    except Exception as e:
        log.error(f"Job {job_id} FAILED: {e}")
        JOB_STATUSES[job_id] = {"status": "error", "progress": 100.0, "message": str(e)}

# --- API Endpoints ---

@app.get("/")
def read_root():
    """Root endpoint to check if the API is alive."""
    return {"status": "Green Agentic API is running (No-Docker Mode)."}


@app.post("/summarize", response_model=SummarizeJobResponse)
async def summarize_document(background_tasks: BackgroundTasks, file: UploadFile, mode: str = "balanced"):
    """
    Starts a new summarization and RAG indexing job.
    """
    log.info(f"Received file: {file.filename} (Type: {file.content_type}) (Mode: {mode})")
    
    file_path, job_id, document_id = await save_upload_file(file)

    background_tasks.add_task(
        run_orchestrator_job, 
        file_path, 
        file.content_type, 
        job_id, 
        document_id,
        mode
    )
    
    return SummarizeJobResponse(
        job_id=job_id,
        document_id=document_id,
        message="Job started. Poll /job-status/{job_id} to get progress."
    )


@app.get("/job-status/{job_id}", response_model=JobStatus)
def get_job_status(job_id: str):
    """
    Endpoint for the frontend to poll for job status.
    """
    status_dict = JOB_STATUSES.get(job_id)
    if not status_dict:
        raise HTTPException(status_code=404, detail="Job not found.")
    
    # --- THIS IS THE FIX for the "got multiple values for keyword argument 'job_id'" error ---
    # The 'status_dict' is the *value* (which doesn't include the job_id).
    # We must manually add the job_id to the dictionary *before* passing it
    # to the Pydantic model.
    try:
        # Create a new dictionary that includes the job_id
        response_data = {"job_id": job_id, **status_dict}
        # Validate and return
        return JobStatus(**response_data)
    except Exception as e:
        log.error(f"Error validating job status for {job_id}: {e}")
        # This will now correctly return a 500 error *if* the data is malformed
        raise HTTPException(status_code=500, detail=f"Error validating status: {status_dict}")
    # --- END OF FIX ---


@app.get("/job-result/{job_id}", response_model=SummaryResponse)
def get_job_result(job_id: str):
    """
    Endpoint for the frontend to get the *final* result
    once the job status is "complete".
    """
    status = JOB_STATUSES.get(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found.")
    if status.get("status") != "complete":
        raise HTTPException(status_code=400, detail="Job is not yet complete.")
        
    return SummaryResponse(**status["result"])


@app.post("/rag-query", response_model=RagQueryResponse)
def query_document(request: RagQueryRequest):
    """
    This is the main "RAG" endpoint (Phase 4).
    """
    log.info(f"RAG Query: Doc ID {request.document_id}, Query: {request.query}")
    
    try:
        context_chunks = storage.search_similar_chunks(
            query=request.query, 
            document_id=request.document_id
        )
    except Exception as e:
        log.error(f"Error during vector search: {e}")
        raise HTTPException(status_code=500, detail="Error searching document.")
    
    if not context_chunks:
        raise HTTPException(status_code=404, detail="No relevant context found for this query.")
    
    try:
        answer, sources = models.run_large_model_rag(
            query=request.query, 
            context_chunks=context_chunks
        )
    except Exception as e:
        log.error(f"Error during RAG answer synthesis: {e}")
        raise HTTPException(status_code=500, detail="Error generating answer.")

    return RagQueryResponse(
        document_id=request.document_id,
        query=request.query,
        answer=answer,
        sources=[chunk.content for chunk in context_chunks]
    )

from src.api.schemas import DocumentResponse

@app.get("/documents", response_model=List[DocumentResponse])
def get_documents():
    """
    List all processed documents with their summaries.
    """
    try:
        docs = storage.list_documents()
        return [DocumentResponse(**doc) for doc in docs]
    except Exception as e:
        log.error(f"Error fetching documents: {e}")
        raise HTTPException(status_code=500, detail="Error fetching documents.")

@app.get("/dashboard-stats")
def get_dashboard_stats():
    """
    Get aggregated statistics for the dashboard.
    """
    try:
        return storage.get_dashboard_stats()
    except Exception as e:
        log.error(f"Error fetching dashboard stats: {e}")
        raise HTTPException(status_code=500, detail="Error fetching dashboard stats.")

# -----------------------------------------------------------
# Authentication Endpoints
# -----------------------------------------------------------

# Security scheme for JWT bearer tokens
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """
    Dependency to get the current authenticated user from JWT token.
    """
    token = credentials.credentials
    payload = auth.decode_access_token(token)
    
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    
    user = storage.get_user_by_id(int(user_id))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user


@app.post("/auth/register", response_model=UserResponse)
def register_user(user_data: UserRegister):
    """
    Register a new user account.
    """
    # Validate email format (basic check)
    if "@" not in user_data.email or "." not in user_data.email:
        raise HTTPException(status_code=400, detail="Invalid email format")
    
    # Validate password strength
    if len(user_data.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")
    
    # Hash the password
    hashed_password = auth.get_password_hash(user_data.password)
    
    # Create user in database
    user = storage.create_user(
        email=user_data.email,
        hashed_password=hashed_password,
        full_name=user_data.full_name
    )
    
    if user is None:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    log.info(f"New user registered: {user_data.email}")
    return UserResponse(**user)


@app.post("/auth/login", response_model=Token)
def login_user(user_data: UserLogin):
    """
    Authenticate user and return JWT access token.
    """
    # Get user from database
    user = storage.get_user_by_email(user_data.email)
    
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Verify password
    if not auth.verify_password(user_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    
    # Create access token
    access_token = auth.create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    log.info(f"User logged in: {user_data.email}")
    return Token(access_token=access_token, token_type="bearer")


@app.get("/auth/me", response_model=UserResponse)
def get_current_user_info(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Get current authenticated user's information.
    """
    return UserResponse(**current_user)
