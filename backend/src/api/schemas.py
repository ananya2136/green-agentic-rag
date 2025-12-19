from pydantic import BaseModel
from typing import List, Optional

# This defines the structure of the Carbon Report in the final summary
class CarbonData(BaseModel):
    carbon_saved_grams: float
    message: str
    total_chunks: int
    chunks_escalated: int
    local_grid_gco2_kwh: float
    remote_grid_gco2_kwh: Optional[float] = None
    compute_location: str
    baseline_cost_gco2e: float = 0.0
    actual_cost_gco2e: float = 0.0
    efficiency_percent: float = 0.0

# This is the response model when a job is FIRST submitted
class SummarizeJobResponse(BaseModel):
    job_id: str
    document_id: str
    message: str

# This is the response model for the /job-status endpoint
class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: float
    message: str

# This is the response model for the FINAL /job-result endpoint
class SummaryResponse(BaseModel):
    document_id: str
    filename: str
    final_summary: str
    carbon_data: CarbonData
    job_id: str

# This is the request model for the /rag-query endpoint
class RagQueryRequest(BaseModel):
    document_id: str
    query: str

# This is the response model for the /rag-query endpoint
class RagQueryResponse(BaseModel):
    document_id: str
    query: str
    answer: str
    sources: List[str] # The text chunks used as context

class DocumentResponse(BaseModel):
    document_id: str
    summary: str
    saved_at: Optional[str] = None
    carbon_saved: Optional[float] = 0.0
    efficiency: Optional[float] = 0.0

# -----------------------------------------------------------
# Authentication Schemas
# -----------------------------------------------------------

class UserRegister(BaseModel):
    """Schema for user registration"""
    email: str
    password: str
    full_name: str

class UserLogin(BaseModel):
    """Schema for user login"""
    email: str
    password: str

class Token(BaseModel):
    """Schema for JWT token response"""
    access_token: str
    token_type: str = "bearer"

class UserResponse(BaseModel):
    """Schema for user information (without password)"""
    id: int
    email: str
    full_name: str
    is_active: bool
    created_at: Optional[str] = None