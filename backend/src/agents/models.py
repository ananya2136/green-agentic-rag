import logging
from transformers import pipeline, AutoModelForSequenceClassification, AutoTokenizer
from sentence_transformers import SentenceTransformer
import ollama
from groq import Groq
from typing import List, Dict, Any, Optional
import torch

from src.core.config import settings

log = logging.getLogger(__name__)

# --- Model Storage ---
# We create a global dictionary to hold all our models in memory.
# This ensures we only load them ONCE when the app starts, not on every request.
models_registry = {}

# --- 1. Light Model (Local Summarizer) ---
def load_light_model():
    """Loads the 'Light' summarization model (DistilBART) from Hugging Face."""
    global models_registry
    if "summarizer_light" not in models_registry:
        try:
            log.info(f"Loading Light Summarizer ({settings.LIGHT_MODEL_REPO})...")
            # --- PRODUCTION FIX: Use GPU if available to speed up local dev ---
            # If the user has a GPU, device=0 will use it. Otherwise, it defaults to CPU (-1).
            device_to_use = 0 if torch.cuda.is_available() else -1
            
            models_registry["summarizer_light"] = pipeline(
                "summarization", 
                model=settings.LIGHT_MODEL_REPO,
                device=device_to_use
            )
            log.info("Light Summarizer loaded successfully.")
        except Exception as e:
            log.error(f"Failed to load Light Summarizer: {e}")
            models_registry["summarizer_light"] = None

def run_light_summarizer(text: str, state: dict) -> str:
    """
    Runs the 'Light' summarizer on a text chunk.
    *** CORRECTED: Now accepts 'state' and tracks usage ***
    """
    pipe = models_registry.get("summarizer_light")
    if pipe is None:
        log.warning("Light summarizer is not available. Skipping.")
        return "Error: Light summarizer not loaded."
    
    try:
        # DistilBART has a token limit. We'll truncate the input.
        max_chunk_length = 1024 
        if len(text) > max_chunk_length:
            text = text[:max_chunk_length]
            
        # Calculate dynamic min_length to avoid hallucinations on short text
        # If text is short, we shouldn't force a long summary.
        # We ensure min_length is at least 5 to get *something*.
        input_len = len(text.split())
        calculated_min = min(30, max(5, input_len // 2))
        
        result = pipe(text, max_length=150, min_length=calculated_min, do_sample=False)
        
        # Track usage for our carbon metrics
        state["model_usage_chars"]["light"] += len(text)
        
        return result[0]['summary_text']
    except Exception as e:
        log.error(f"Error in light summarizer: {e}")
        return "Summary generation failed."

# --- 2. Medium Model (Local LLM) ---
def load_medium_model():
    """Confirms that the 'Medium' model (Ollama) is available."""
    global models_registry
    try:
        log.info(f"Checking for Medium Model ({settings.OLLAMA_MEDIUM_MODEL})...")
        models_registry["ollama_client"] = ollama.Client(host=settings.OLLAMA_HOST)
        models_registry["ollama_client"].show(settings.OLLAMA_MEDIUM_MODEL)
        log.info(f"Ollama client connected. Medium Model '{settings.OLLAMA_MEDIUM_MODEL}' is available.")
    except Exception as e:
        log.error(f"Failed to connect to Ollama or find model '{settings.OLLAMA_MEDIUM_MODEL}'.")
        log.error("Please ensure Ollama is running and you have run: ollama pull gemma:2b")
        models_registry["ollama_client"] = None

def run_medium_summarizer(text: str, state: dict) -> str:
    """
    Runs the 'Medium' summarizer (Ollama) on a text chunk.
    *** CORRECTED: Now accepts 'state' ***
    """
    client = models_registry.get("ollama_client")
    if client is None:
        log.warning("Medium summarizer (Ollama) is not available. Skipping.")
        return "Error: Medium summarizer not loaded."

    prompt = f"""
    You are an expert summarization model. 
    Provide a concise, factual summary of the following text.
    Do not add any preamble, introduction, or conversational fluff.
    
    TEXT:
    {text}
    
    SUMMARY:
    """
    
    try:
        response = client.chat(
            model=settings.OLLAMA_MEDIUM_MODEL,
            messages=[{'role': 'user', 'content': prompt}]
        )
        
        # Track usage for our carbon metrics
        state["model_usage_chars"]["medium"] += len(text)
        
        return response['message']['content']
    except Exception as e:
        log.error(f"Error in medium summarizer: {e}")
        return "Summary generation failed."

# --- 3. Large Model (Groq Llama 3) ---
def load_large_model():
    """Confirms the 'Large' model (Groq) API client."""
    global models_registry
    try:
        log.info("Configuring Large Model (Groq)...")
        if not settings.GROQ_API_KEY:
             raise ValueError("GROQ_API_KEY is not set in the .env file.")
             
        client = Groq(api_key=settings.GROQ_API_KEY)
        models_registry["summarizer_large"] = client
        log.info(f"Large Model (Groq: {settings.LARGE_MODEL_NAME}) configured successfully.")
    except Exception as e:
        log.error(f"Failed to configure Groq: {e}")
        print(f"❌ Groq Configuration Error: {e}")
        models_registry["summarizer_large"] = None

def run_large_model_compile(text_of_summaries: str, state: dict) -> str:
    """
    Runs the 'Large' model to compile the final executive summary.
    *** CORRECTED: Now accepts 'state' ***
    """
    client = models_registry.get("summarizer_large")
    if client is None:
        log.warning("Large summarizer (Groq) is not available. Compiling via Medium model.")
        return run_medium_summarizer(text_of_summaries, state)

    prompt = f"""
    You are an expert editor. You will be given a large collection of
    small, disconnected summaries from a document.
    Your job is to synthesize these summaries into a single,
    coherent, well-written executive summary.
    
    CRITICAL INSTRUCTIONS:
    - STRICTLY use ONLY the information present in the summaries below
    - DO NOT add any external information, examples, or unrelated content
    - DO NOT invent, assume, or extrapolate beyond what is explicitly stated
    - Synthesize the provided summaries into a cohesive narrative
    - Be concise, accurate, and factual
    - If the summaries are about a specific topic, stay focused on that topic only
    
    SUMMARIES:
    {text_of_summaries}
    
    EXECUTIVE SUMMARY:
    """
    
    import time
    max_retries = 3
    for attempt in range(max_retries):
        try:
            completion = client.chat.completions.create(
                model=settings.LARGE_MODEL_NAME,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=2000,
            )
            
            response_text = completion.choices[0].message.content
            
            # Track usage for our carbon metrics
            state["model_usage_chars"]["large"] += len(text_of_summaries)
            
            return response_text
        except Exception as e:
            if "429" in str(e):
                log.warning(f"Groq Rate Limit hit. Retrying in 5s (Attempt {attempt+1}/{max_retries})...")
                time.sleep(5)
            else:
                log.error(f"Error in Groq summarizer: {e}")
                return f"Final summary generation failed: {e}"
    
    return "Summary failed due to Rate Limits."

def run_large_model_rag(query: str, context_chunks: List) -> (str, List[str]):
    """Runs the 'Large' model to answer a RAG query."""
    client = models_registry.get("summarizer_large")
    if client is None:
        log.warning("Large model (Groq) is not available. Cannot answer RAG query.")
        return "Error: RAG model not loaded. Please ensure your GROQ_API_KEY is set.", []

    context_str = "\n\n---\n\n".join([chunk.content for chunk in context_chunks])
    
    prompt = f"""
    You are an expert Q&A assistant. Answer the user's query *only* based on
    the provided context. Be concise and factual.
    
    CONTEXT:
    {context_str}
    
    QUERY:
    {query}
    
    ANSWER:
    """
    
    import time
    max_retries = 3
    for attempt in range(max_retries):
        try:
            completion = client.chat.completions.create(
                model=settings.LARGE_MODEL_NAME,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
            )
            response_text = completion.choices[0].message.content
            sources = [chunk.content for chunk in context_chunks]
            return response_text, sources
        except Exception as e:
             if "429" in str(e):
                log.warning(f"Groq Rate Limit hit (RAG). Retrying in 5s (Attempt {attempt+1}/{max_retries})...")
                time.sleep(5)
             else:
                log.error(f"Error in RAG model: {e}")
                return "Failed to generate answer.", []
                
    return "Answer failed due to Groq Rate Limits.", []

# --- 4. Accuracy-Checker Model (Local NLI) ---
def load_checker_model():
    """Loads the 'Accuracy Checker' (NLI) model from Hugging Face."""
    global models_registry
    if "checker_model" not in models_registry:
        try:
            log.info(f"Loading Accuracy Checker ({settings.CHECKER_MODEL_REPO})...")
            models_registry["checker_tokenizer"] = AutoTokenizer.from_pretrained(settings.CHECKER_MODEL_REPO)
            models_registry["checker_model"] = AutoModelForSequenceClassification.from_pretrained(settings.CHECKER_MODEL_REPO)
            log.info("Accuracy Checker loaded successfully.")
        except Exception as e:
            log.error(f"Failed to load Accuracy Checker: {e}")
            models_registry["checker_model"] = None
            models_registry["checker_tokenizer"] = None

def run_accuracy_check(original_text: str, summary: str) -> bool:
    """
    Checks if the summary is factually consistent with the original text.
    Returns True if accurate, False if not.
    """
    tokenizer = models_registry.get("checker_tokenizer")
    model = models_registry.get("checker_model")
    
    if not tokenizer or not model:
        log.warning("Accuracy checker not available. Assuming all summaries are accurate.")
        return True
        
    try:
        # We format the input as [PREMISE] text [HYPOTHESIS] summary
        input_text = f"[PREMISE] {original_text} [HYPOTHESIS] {summary}"
        
        tokenized_input = tokenizer(input_text, return_tensors="pt", max_length=512, truncation=True)
        
        logits = model(**tokenized_input).logits
        
        # The model outputs 3 scores: [Contradiction, Neutral, Entailment]
        prediction = logits.argmax().item()
        
        # 2 = "Entailment" (The summary is supported by the text)
        return prediction == 2
        
    except Exception as e:
        log.error(f"Error in accuracy checker: {e}. Defaulting to 'True'.")
        return True

# --- 5. Embedding Model (Local RAG) ---
def load_embedding_model():
    """Loads the 'Embedding' model from Hugging Face."""
    global models_registry
    if "embedding_model" not in models_registry:
        try:
            log.info(f"Loading Embedding Model ({settings.EMBEDDING_MODEL_REPO})...")
            models_registry["embedding_model"] = SentenceTransformer(
                settings.EMBEDDING_MODEL_REPO
            )
            log.info("Embedding Model loaded successfully.")
        except Exception as e:
            log.error(f"Failed to load Embedding Model: {e}")
            models_registry["embedding_model"] = None

def get_embedding_model() -> Optional[SentenceTransformer]:
    """
    Returns the loaded embedding model instance.
    *** FIX: This is the getter function for storage.py to use. ***
    """
    return models_registry.get("embedding_model")

# --- Main Loader ---
def load_all_models():
    """
    Called once on API startup (in main.py) to load all
    local models into memory.
    """
    log.info("--- Loading all local AI models... ---")
    load_light_model()
    load_medium_model()
    load_large_model()
    load_checker_model()
    load_embedding_model()
    log.info("--- All models loaded. API is ready. ---")