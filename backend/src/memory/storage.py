import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from sqlalchemy import create_engine, Column, String, Text, DateTime, func, Float, Integer, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker

from chromadb import Client
from chromadb.config import Settings as ChromaSettings

from src.core.config import settings
from src.agents import models

# -----------------------------------------------------------
# Logging Setup
# -----------------------------------------------------------
log = logging.getLogger("storage")
log.setLevel(logging.INFO)

# -----------------------------------------------------------
# SQLAlchemy Setup (SQLite Metadata DB)
# -----------------------------------------------------------
Base = declarative_base()
DBSessionLocal = None
engine = None

def init_sqlite():
    global DBSessionLocal, engine
    try:
        os.makedirs(os.path.dirname(settings.DATABASE_URL.replace("sqlite:///", "")), exist_ok=True)
        engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
        DBSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        Base.metadata.create_all(bind=engine)
        log.info(f"SQLite initialized at {settings.DATABASE_URL}")

    except Exception as e:
        log.error(f"Failed to initialize SQLite DB: {e}")

# -----------------------------------------------------------
# ChromaDB Setup (Vector Database)
# -----------------------------------------------------------
chroma_client = Client(
    ChromaSettings(
        persist_directory=settings.VECTOR_DB_PATH,
        allow_reset=True
    )
)

# -----------------------------------------------------------
# Chunk Model (for embeddings)
# -----------------------------------------------------------
class ChunkModel(Base):
    __tablename__ = "chunks"

    id = Column(String, primary_key=True, index=True)
    document_id = Column(String, index=True)
    chunk_index = Column(String)
    text = Column(Text)
    added_at = Column(DateTime(timezone=True), server_default=func.now())

# -----------------------------------------------------------
# Document Model (for final summary)
# -----------------------------------------------------------
class DocumentModel(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, index=True)
    summary = Column(Text)
    saved_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Analytics columns
    carbon_saved_grams = Column(Float, default=0.0)
    processing_time_seconds = Column(Float, default=0.0)
    total_chunks = Column(Integer, default=0)
    efficiency_percent = Column(Float, default=0.0)

# -----------------------------------------------------------
# User Model (for authentication)
# -----------------------------------------------------------
class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# CRITICAL: Initialize SQLite AFTER model definitions so tables get created
init_sqlite()


# -----------------------------------------------------------
# Chunk Storage Functions
# -----------------------------------------------------------

def store_chunks(document_id: str, chunks: List[Any]):
    """
    Stores text chunks in SQLite + embeddings in ChromaDB.
    Handles both dicts and Pydantic 'Chunk' objects.
    Generates embeddings if missing.
    """
    try:
        collection = chroma_client.get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"}
        )

        db = DBSessionLocal()
        
        # Get embedding model once
        embedding_model = models.get_embedding_model()
        if not embedding_model:
            log.warning("Embedding model not loaded. RAG search will not work for this doc.")

        for idx, c in enumerate(chunks):
            chunk_id = f"{document_id}_{idx}"
            
            # 1. Normalize content (Dict vs Pydantic)
            text_content = ""
            if isinstance(c, dict):
                text_content = c.get("text") or c.get("content") or ""
            else:
                # Assume Pydantic Chunk object
                text_content = getattr(c, "content", "")

            if not text_content:
                continue

            # 2. Store in SQLite
            db_chunk = ChunkModel(
                id=chunk_id,
                document_id=document_id,
                chunk_index=str(idx),
                text=text_content
            )
            db.merge(db_chunk)

            # 3. Generate Embedding (if needed) & Store in Chroma
            if embedding_model:
                # Check if embedding already exists (if passed in dict)
                embedding = None
                if isinstance(c, dict):
                    embedding = c.get("embedding")
                
                if not embedding:
                    # Generate it on the fly
                    embedding = embedding_model.encode(text_content).tolist()
                
                collection.upsert(
                    ids=[chunk_id],
                    embeddings=[embedding],
                    metadatas=[{"document_id": document_id, "chunk_index": idx}],
                    documents=[text_content],
                )

        db.commit()
        db.close()

        log.info(f"Stored {len(chunks)} chunks for document {document_id}")
        return True

    except Exception as e:
        log.error(f"Failed to store chunks: {e}")
        return False


def search_similar_chunks(query: str, document_id: str, k: int = 5) -> List[Any]:
    """
    Searches for chunks similar to the query in the given document.
    Returns keys: 'content', 'score'.
    """
    try:
        collection = chroma_client.get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"}
        )
        
        # Get embedding model
        embedding_model = models.get_embedding_model()
        if not embedding_model:
            log.warning("Embedding model not loaded. Cannot perform RAG search.")
            return []
            
        # Generate query embedding
        query_embedding = embedding_model.encode(query).tolist()
        
        # Search
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            where={"document_id": document_id}
        )
        
        # Format results
        # Chroma returns lists of lists (for batch queries)
        # We only sent one query, so we look at index 0
        if not results['documents'] or not results['documents'][0]:
            return []
            
        found_chunks = []
        for i, doc_text in enumerate(results['documents'][0]):
             # We create a simple object or dict that mimics the 'Chunk' interface expected by the RAG runner
             # The RAG runner (models.run_large_model_rag) expects objects with a '.content' attribute
             
             # Mimic object
             class ResultChunk:
                 def __init__(self, content):
                     self.content = content
                     
             found_chunks.append(ResultChunk(content=doc_text))
             
        return found_chunks
        
    except Exception as e:
        log.error(f"Failed to search similar chunks: {e}")
        raise e


def retrieve_chunks(document_id: str):
    db = DBSessionLocal()
    try:
        rows = db.query(ChunkModel).filter(ChunkModel.document_id == document_id).all()
        return [{"text": r.text, "index": r.chunk_index} for r in rows]
    finally:
        db.close()


def delete_chunks(document_id: str):
    try:
        db = DBSessionLocal()
        db.query(ChunkModel).filter(ChunkModel.document_id == document_id).delete()
        db.commit()
        db.close()

        collection = chroma_client.get_or_create_collection("documents")
        all_ids = [f"{document_id}_{i}" for i in range(5000)]
        collection.delete(ids=all_ids)

        log.info(f"Deleted chunks for document {document_id}")

    except Exception as e:
        log.error(f"Failed to delete chunks: {e}")

# -----------------------------------------------------------
# Initialization (Called by Main.py)
# -----------------------------------------------------------
def init_database():
    """
    Called by main.py on startup. 
    SQLite and Chroma are already initialized on import, 
    so this is just a compatibility wrapper/health check.
    """
    if not engine or not chroma_client:
        log.error("Databases not initialized properly!")
    else:
        log.info("Databases initialized.")

# -----------------------------------------------------------
# FINAL SUMMARY STORAGE
# -----------------------------------------------------------

def store_document_data(job_id: str, summary: str, chunks: List[Any], carbon_meta: Dict[str, Any] = None):
    """
    Stores the final summary generated by the reduce agent.
    Updated to match Orchestrator signature.
    ADDED: carbon_meta for dashboard analytics.
    """
    document_id = job_id 
    
    if carbon_meta is None:
        carbon_meta = {}

    # 1. Store the summary and carbon stats
    try:
        db = DBSessionLocal()
        doc = db.get(DocumentModel, document_id)

        if doc:
            doc.summary = summary
            doc.carbon_saved_grams = carbon_meta.get("carbon_saved_grams", 0.0)
            doc.processing_time_seconds = carbon_meta.get("processing_time_seconds", 0.0)
            doc.total_chunks = carbon_meta.get("total_chunks", 0)
            doc.efficiency_percent = carbon_meta.get("efficiency_percent", 0.0)
        else:
            doc = DocumentModel(
                id=document_id, 
                summary=summary,
                carbon_saved_grams = carbon_meta.get("carbon_saved_grams", 0.0),
                processing_time_seconds = carbon_meta.get("processing_time_seconds", 0.0),
                total_chunks = carbon_meta.get("total_chunks", 0),
                efficiency_percent = carbon_meta.get("efficiency_percent", 0.0)
            )
            db.add(doc)

        db.commit()
        db.close()
        log.info(f"Final summary and stats stored for document {document_id}")
    except Exception as e:
        log.error(f"Failed to store final summary: {e}")
        
    # 2. Store the chunks
    if chunks:
        # FIX: Actually store the chunks!
        success = store_chunks(document_id, chunks)
        if success:
            log.info(f"RAG: Stored {len(chunks)} chunks for {document_id}")
        else:
            log.error(f"RAG: Failed to store chunks for {document_id}")
            
    return {"status": "ok", "document_id": document_id}


def get_document_data(document_id: str) -> Optional[str]:
    """
    Retrieve the final summary (used by UI).
    """
    try:
        db = DBSessionLocal()
        doc = db.get(DocumentModel, document_id)
        db.close()
        return doc.summary if doc else None

    except Exception as e:
        log.error(f"Failed to fetch document summary: {e}")
        return None


def delete_document_data(document_id: str):
    try:
        db = DBSessionLocal()
        doc = db.get(DocumentModel, document_id)
        if doc:
            db.delete(doc)
            db.commit()
        db.close()
        log.info(f"Deleted document-level data for {document_id}")
    except Exception as e:
        log.error(f"Failed to delete document summary: {e}")


def list_documents() -> List[Dict[str, Any]]:
    """
    List all stored documents.
    """
    try:
        db = DBSessionLocal()
        docs = db.query(DocumentModel).order_by(DocumentModel.saved_at.desc()).all()
        result = []
        for doc in docs:
            result.append({
                "document_id": doc.id,
                "summary": doc.summary,
                "saved_at": doc.saved_at.isoformat() if doc.saved_at else None,
                # Include stats in list for potential UI usage
                "carbon_saved": doc.carbon_saved_grams,
                "efficiency": doc.efficiency_percent
            })
        db.close()
        return result
    except Exception as e:
        log.error(f"Failed to list documents: {e}")
        return []

def get_dashboard_stats() -> Dict[str, Any]:
    """
    Aggregates data for the dashboard.
    """
    try:
        db = DBSessionLocal()
        docs = db.query(DocumentModel).all()
        
        total_docs = len(docs)
        total_carbon_saved = sum([d.carbon_saved_grams or 0.0 for d in docs])
        avg_efficiency = sum([d.efficiency_percent or 0.0 for d in docs]) / total_docs if total_docs > 0 else 0
        
        # Simple trend data (group by date) - For demo purposes, we will just return raw list mapped
        # In a real app, you'd do SQL aggregation
        
        # Create 7-day trend placeholder, populating with real data where available
        # This is a basic implementation
        trends = []
        
        # Sort by date
        sorted_docs = sorted(docs, key=lambda x: x.saved_at if x.saved_at else datetime.min)
        
        # We'll just return the raw data points properly formatted for the chart
        for d in sorted_docs:
            if d.saved_at:
                trends.append({
                    "date": d.saved_at.strftime("%b %d"),
                    "savings": d.carbon_saved_grams,
                    "baseline": (d.carbon_saved_grams / (d.efficiency_percent/100)) if d.efficiency_percent and d.efficiency_percent > 0 else 0
                })
        
        db.close()
        
        return {
            "total_carbon_saved": total_carbon_saved,
            "total_docs": total_docs,
            "avg_efficiency": avg_efficiency,
            "carbon_trend": trends[-7:] if len(trends) > 7 else trends # Last 7 points
        }
    except Exception as e:
        log.error(f"Failed to get dashboard stats: {e}")
        return {
            "total_carbon_saved": 0, 
            "total_docs": 0, 
            "avg_efficiency": 0, 
            "carbon_trend": []
        }

# -----------------------------------------------------------
# USER MANAGEMENT FUNCTIONS
# -----------------------------------------------------------

def create_user(email: str, hashed_password: str, full_name: str) -> Optional[Dict[str, Any]]:
    """
    Create a new user account.
    Returns user info if successful, None if email already exists.
    """
    try:
        db = DBSessionLocal()
        
        # Check if user already exists
        existing_user = db.query(UserModel).filter(UserModel.email == email).first()
        if existing_user:
            db.close()
            return None
        
        # Create new user
        new_user = UserModel(
            email=email,
            hashed_password=hashed_password,
            full_name=full_name
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        user_data = {
            "id": new_user.id,
            "email": new_user.email,
            "full_name": new_user.full_name,
            "is_active": new_user.is_active,
            "created_at": new_user.created_at.isoformat() if new_user.created_at else None
        }
        
        db.close()
        log.info(f"Created new user: {email}")
        return user_data
        
    except Exception as e:
        log.error(f"Failed to create user: {e}")
        return None


def get_user_by_email(email: str):
    """
    Retrieve a user by email address.
    Returns the full UserModel (including hashed_password) for authentication.
    """
    try:
        db = DBSessionLocal()
        user = db.query(UserModel).filter(UserModel.email == email).first()
        db.close()
        return user
    except Exception as e:
        log.error(f"Failed to get user by email: {e}")
        return None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Retrieve a user by ID.
    Returns user info (without password) for display purposes.
    """
    try:
        db = DBSessionLocal()
        user = db.get(UserModel, user_id)
        
        if not user:
            db.close()
            return None
        
        user_data = {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat() if user.created_at else None
        }
        
        db.close()
        return user_data
        
    except Exception as e:
        log.error(f"Failed to get user by ID: {e}")
        return None

