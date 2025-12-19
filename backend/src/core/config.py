from pydantic_settings import BaseSettings, SettingsConfigDict
import os
from typing import Optional

# Get the absolute path of the directory where this file is
# e.g., /path/to/project/backend/src/core
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Go up two levels to get the /path/to/project/backend/ directory
# This is where your .env file should be
ENV_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "..", ".env"))


class Settings(BaseSettings):
    """
    This class loads all settings from environment variables.
    It automatically reads from the .env file in the `backend/` directory.
    """
    
    # --- Cloud API Keys ---
    # (Get this from Google AI Studio)
    GROQ_API_KEY: str = ""  # Set via environment variable
    LARGE_MODEL_NAME: str = "llama-3.1-8b-instant" # User specified model
    ELECTRICITY_MAPS_API_KEY: Optional[str] = "t6LdqQgs3XZRGxg2VIXj"

    # --- Local Model Configuration ---
    # This is the "Medium" model we run with Ollama
    OLLAMA_MEDIUM_MODEL: str = "gemma:2b"
    
    OLLAMA_HOST: str = "http://localhost:11434"

    # This is the "Light" summarizer from Hugging Face
    LIGHT_MODEL_REPO: str = "sshleifer/distilbart-cnn-12-6"
    
    # This is the "Accuracy Checker" (NLI) model from Hugging Face
    
    CHECKER_MODEL_REPO: str = "Moritz/robert-base-c-fact-all"

    # This is the "Embedding" model for RAG
    EMBEDDING_MODEL_REPO: str = "sentence-transformers/all-MiniLM-L6-v2"

    # --- Database Configuration (File-based) ---
    # We will store the vector DB in a folder called 'local_db'
    VECTOR_DB_PATH: str = "./local_db/chroma"
    # We will use SQLite for metadata
    DATABASE_URL: str = "sqlite:///./agentic_db.sqlite"

    # --- Carbon Scheduler Settings ---
    # Baseline for carbon savings comparison (in gCO2eq/kWh)
    # This represents a "standard" data center on a mixed-carbon grid
    BASELINE_GRID_INTENSITY: float = 450.0 # (e.g., avg US grid)
    # This is a *simulation* of our local grid (e.g., Pune, India)
    # This is a high-carbon grid, which encourages using our 'Light' models
    LOCAL_GRID_INTENSITY: float = 700.0 

    # --- Triage Agent Settings ---
    # Strategy for `unstructured` library. 
    # "hi_res" enables visual, agentic parsing.
    # "fast" is text-only.
    TRIAGE_STRATEGY: str = "fast"
    
    # --- Authentication Settings ---
    # Secret key for JWT token signing (change in production!)
    JWT_SECRET_KEY: str = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    
    # This tells pydantic-settings to load from the .env file
    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        extra="ignore"  # Ignore any extra env vars
    )


# Create a single, global instance of the settings that we can
# import and use anywhere else in the application.
settings = Settings()