import logging
import concurrent.futures
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END



# Import all our custom components
# Ensure these modules exist in your project structure
from src.agents import triage, models
from src.memory import storage
from src.core import scheduler
from src.core.config import settings
from src.monitoring import metrics 
from src.carbon_router import analyze_pdf_carbon_impact 

# --- Set up logging ---
log = logging.getLogger(__name__)

# --- Global Job Status ---
# This dictionary tracks the status of long-running jobs for the API/Frontend to poll.
JOB_STATUSES: Dict[str, Dict[str, Any]] = {}


# --- Agent State ---
# This class defines the "memory" of our agent.
# It's the data structure that gets passed from one step (node) to the next.
class AgentState(TypedDict):
    job_id: str
    document_id: str
    file_path: str
    file_type: str
    job_mode: str
    
    # Data from Triage
    chunks: List[triage.Chunk]
    
    # Data from Summarization
    summaries: List[str]
    failed_chunks: List[triage.Chunk] 
    
    # Final outputs
    final_summary: str
    
    # Metrics
    total_chunks: int
    chunks_escalated: int
    carbon_report: Dict[str, Any]
    # This dictionary will be populated by the model runners
    model_usage_chars: Dict[str, int]
    
    # Carbon Router Result (Populated if running in eco mode)
    carbon_routing_result: Optional[Dict[str, Any]]


# --- AGENT NODES ---

def start_job(state: AgentState) -> AgentState:
    """Node 1: Initializes the job and status."""
    job_id = state["job_id"]
    log.info(f"Job {job_id}: [Node 1/8] Starting job.")
    
    # Initialize the model usage tracker in the state
    state["model_usage_chars"] = {"light": 0, "medium": 0, "large": 0} 
    
    JOB_STATUSES[job_id] = {
        "job_id": job_id,
        "status": "processing",
        "progress": 5.0,
        "message": "Starting job..."
    }
    # We must return the *full* state dictionary
    return state


def triage_document(state: AgentState) -> AgentState:
    """Node 2: The "Eyes" of the agent. Performs visual smart-chunking."""
    job_id = state["job_id"]
    log.info(f"Job {job_id}: [Node 2/8] Triaging document...")
    JOB_STATUSES[job_id]["progress"] = 15.0
    JOB_STATUSES[job_id]["message"] = "Step 1/4: Analyzing document layout (Triage)..."
    
    chunks = triage.triage_document(
        file_path=state["file_path"], 
        file_type=state["file_type"], 
        strategy=settings.TRIAGE_STRATEGY 
    )
    
    if not chunks:
        raise ValueError("Triage returned no chunks. Cannot proceed.")
        
    log.info(f"Job {job_id}: Triage complete. Found {len(chunks)} chunks.")
    
    # We return the *changes* to the state
    return {
        "chunks": chunks,
        "total_chunks": len(chunks)
    }


def map_summarize_chunks(state: AgentState) -> AgentState:
    """
    Node 3: The "Map" step. Runs the LOW-ENERGY "Light-Summarizer" using PARALLELISM.
    """
    job_id = state["job_id"]
    log.info(f"Job {job_id}: [Node 3/8] Summarizing (Map) with Light model using parallelism...")
    JOB_STATUSES[job_id]["progress"] = 25.0
    JOB_STATUSES[job_id]["message"] = "Step 2/4: Running 'Light' summary on all chunks..."

    chunks = state["chunks"]
    summaries = []
    total_chunks = state["total_chunks"]
    
    # --- PARALLELISM IMPLEMENTATION ---
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        # Submit the model run function for each chunk
        futures = {executor.submit(
            models.run_light_summarizer, 
            chunk.content, 
            state # Pass state for usage tracking
        ): chunk for chunk in chunks}
        
        # Collect results and update progress
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            summary = future.result()
            summaries.append(summary)
            
            # Update progress for the UI (30% of the total work is here)
            progress = 25.0 + ( (i + 1) / total_chunks ) * 30.0 
            JOB_STATUSES[job_id]["progress"] = progress
            JOB_STATUSES[job_id]["message"] = f"Step 2/4: Running 'Light' summary... ({i+1}/{total_chunks})"
    # --- END PARALLELISM ---

    log.info(f"Job {job_id}: 'Light' summary (Map) complete.")
    return {"summaries": summaries}


def check_accuracy(state: AgentState) -> AgentState:
    """
    Node 4: The "Self-Correction" check. 
    Checks factual consistency. Sorts chunks into passed/failed.
    """
    job_id = state["job_id"]
    log.info(f"Job {job_id}: [Node 4/8] Checking accuracy...")
    JOB_STATUSES[job_id]["progress"] = 55.0
    JOB_STATUSES[job_id]["message"] = "Step 3/4: Checking summary accuracy..."

    chunks = state["chunks"]
    summaries = state["summaries"]
    failed_chunks = []
    passed_summaries = []
    total_chunks = state["total_chunks"]

    for i, (chunk, summary) in enumerate(zip(chunks, summaries)):
        # Run the specialized NLI model to check for factual support
        is_accurate = models.run_accuracy_check(original_text=chunk.content, summary=summary)
        
        if not is_accurate:
            failed_chunks.append(chunk) 
        else:
            passed_summaries.append(summary)
            
        # Update progress
        progress = 55.0 + ( (i + 1) / total_chunks ) * 15.0 
        JOB_STATUSES[job_id]["progress"] = progress

    log.info(f"Job {job_id}: Accuracy check complete. {len(failed_chunks)} chunks failed.")
    
    return {
        "failed_chunks": failed_chunks,
        "summaries": passed_summaries, 
        "chunks_escalated": len(failed_chunks)
    }


def should_rerun(state: AgentState) -> str:
    """Conditional Edge: Decides whether to escalate or proceed."""
    if state["failed_chunks"]:
        log.info(f"Job {state['job_id']}: [Decision] Failed chunks detected. Escalating to Medium model.")
        return "escalate"
    else:
        log.info(f"Job {state['job_id']}: [Decision] All chunks passed. Proceeding to compile.")
        return "compile"


def map_escalate_chunks(state: AgentState) -> AgentState:
    """Node 5 (Conditional): Escalation step (Medium model) for failed chunks."""
    job_id = state["job_id"]
    failed_chunks = state["failed_chunks"]
    log.info(f"Job {job_id}: [Node 5/8] Escalating {len(failed_chunks)} failed chunks...")
    JOB_STATUSES[job_id]["progress"] = 75.0
    JOB_STATUSES[job_id]["message"] = f"Step 3/4: Escalating {len(failed_chunks)} failed chunks to 'Medium' model..."
    
    escalated_summaries = state["summaries"] 
    
    # --- Parallelism for Escalation ---
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(
            models.run_medium_summarizer, 
            chunk.content, 
            state
        ): chunk for chunk in failed_chunks}
        
        for future in concurrent.futures.as_completed(futures):
            summary = future.result()
            escalated_summaries.append(summary)
    # --- END PARALLELISM ---

    log.info(f"Job {job_id}: Escalation complete.")
    return {"summaries": escalated_summaries, "failed_chunks": []}


def reduce_compile_summary(state: AgentState) -> AgentState:
    """
    Node 6: The "Reduce" step. Compiles all small summaries into one final executive summary.
    """
    job_id = state["job_id"]
    log.info(f"Job {job_id}: [Node 6/8] Compiling final summary (Reduce)...")
    JOB_STATUSES[job_id]["progress"] = 85.0
    JOB_STATUSES[job_id]["message"] = "Step 4/4: Compiling final executive summary..."

    # Join the summaries
    combined_text = "\n\n".join(state["summaries"])

    # Call the powerful model (Gemini) to synthesize them
    # Ensure run_final_compiler is implemented in src/agents/models.py
    final_summary = models.run_large_model_compile(combined_text, state)

    log.info(f"Job {job_id}: Final summary compiled.")
    return {"final_summary": final_summary}


def store_for_rag(state: AgentState) -> AgentState:
    """
    Node 7: Stores the data for Retrieval Augmented Generation (RAG).
    """
    job_id = state["job_id"]
    log.info(f"Job {job_id}: [Node 7/8] Storing for RAG...")
    JOB_STATUSES[job_id]["message"] = "Indexing data for search..."

    # Call storage module to save vectors
    storage.store_document_data(
        job_id=job_id,
        summary=state["final_summary"],
        chunks=state["chunks"]
    )
    
    log.info(f"Job {job_id}: RAG storage complete.")
    return state


def calculate_carbon(state: AgentState) -> AgentState:
    """
    Node 8: Final Reporting. Calculates carbon savings and logs metrics.
    """
    job_id = state["job_id"]
    log.info(f"Job {job_id}: [Node 8/8] Calculating final carbon metrics...")
    JOB_STATUSES[job_id]["progress"] = 100.0
    JOB_STATUSES[job_id]["message"] = "Job Complete."
    JOB_STATUSES[job_id]["status"] = "completed"

    # Calculate savings using the scheduler
    report = scheduler.calculate_carbon_savings(
        job_id=job_id,
        state=state 
    )
    
    # Log final metrics
    metrics.log_job_metrics(job_id, report, state)
    
    # Save the carbon stats to the DB (updating the document record)
    storage.store_document_data(
        job_id=job_id,
        summary=state["final_summary"],
        chunks=[], # Already stored or not needed here
        carbon_meta=report
    )
    
    log.info(f"Job {job_id}: Carbon report generated: {report}")
    return {"carbon_report": report}


def run_carbon_router(state: AgentState) -> AgentState:
    """
    Node: Runs the specialized Carbon Router logic for Eco Mode.
    Bypasses the standard summarization flow.
    """
    job_id = state["job_id"]
    log.info(f"Job {job_id}: [Eco Mode] Running Carbon Router...")
    JOB_STATUSES[job_id]["progress"] = 50.0
    JOB_STATUSES[job_id]["message"] = "Analyzing Carbon Footprint & Routing..."
    
    try:
        # Run the analysis
        result = analyze_pdf_carbon_impact(state["file_path"])
        
        # Calculate metrics for the frontend
        actual_carbon = result["recommended_server"]["carbon_grams"]
        
        # Use simple baseline: average of all options, or worst case?
        all_options = result["all_options"]
        if len(all_options) > 1:
            params = [x["carbon_grams"] for x in all_options]
            baseline_carbon = sum(params) / len(params)
        else:
            baseline_carbon = actual_carbon * 1.5 

        saved_carbon = max(0, baseline_carbon - actual_carbon)
        if baseline_carbon > 0:
            efficiency = ((baseline_carbon - actual_carbon) / baseline_carbon) * 100.0
        else:
            efficiency = 0.0

        # We store the result in the state
        # We also populate a "fake" final_summary so the UI has something to show if it relies on that field
        summary_text = (
            f" CARBON ROUTER ANALYSIS \n"
            f"----------------------------------------\n"
            f"Recommended Server: {result['recommended_server']['server_name']}\n"
            f"Carbon Saved: {result['explanation']}\n"
            f"Estimated Tokens: {result['estimated_tokens']}\n"
            f"Data Source: {result['data_source']}\n"
        )
        
        # Save the result to history (DB)
        # We pass an empty list for chunks since Eco Mode doesn't do chunk-based RAG
        # We construct the carbon_meta dictionary from the local variables or the 'result'
        
        carbon_meta_for_db = {
            "carbon_saved_grams": saved_carbon,
            "processing_time_seconds": result["recommended_server"]["processing_time_seconds"],
            "total_chunks": 1,
            "efficiency_percent": efficiency
        }

        storage.store_document_data(
            job_id=job_id,
            summary=summary_text,
            chunks=[], 
            carbon_meta=carbon_meta_for_db
        )

        JOB_STATUSES[job_id]["progress"] = 100.0
        JOB_STATUSES[job_id]["message"] = "Carbon Routing Analysis Complete."
        JOB_STATUSES[job_id]["status"] = "complete" # Mark as complete here since we jump to END
        
        # Hack: Populate result directly here to ensure main.py picks it up if it reads from JOB_STATUSES immediately?
        # main.py reads valid results from JOB_STATUSES["result"] when status is complete.
        # But `run_orchestrator_job` in `main.py` overwrites JOB_STATUSES at the end...
        # Wait, `run_orchestrator_job` lines 162-173 overwrites it.
        # So we just need to return state, and `main.py` will handle the rest?
        # `main.py` uses `final_state["final_summary"]`.
        # It also does `final_carbon_data = { **final_state["carbon_report"] }`.
        # We should probably populate `carbon_report` with something meaningful too?
        
        return {
            "final_summary": summary_text,
            "carbon_routing_result": result,
            "carbon_report": {
                 # Map to CarbonData schema required by frontend/API
                 "carbon_saved_grams": saved_carbon,
                 "message": result["explanation"],
                 "total_chunks": 1, # Dummy value
                 "chunks_escalated": 0, # N/A
                 "local_grid_gco2_kwh": result["recommended_server"]["carbon_intensity"], 
                 "remote_grid_gco2_kwh": None,
                 "compute_location": result["recommended_server"]["region"],
                 # New fields
                 "baseline_cost_gco2e": baseline_carbon,
                 "actual_cost_gco2e": actual_carbon,
                 "efficiency_percent": efficiency
            }
        }
        
    except Exception as e:
        log.error(f"Carbon Router Failed: {e}")
        raise e


def route_start_job(state: AgentState) -> str:
    """
    Conditional Edge: Routes based on Job Mode.
    """
    mode = state.get("job_mode", "balanced").lower()
    if mode == "eco":
        return "eco_mode"
    else:
        return "standard_mode"


# --- Build the Graph ---

log.info("Building Agentic Graph (Orchestrator)...")

workflow = StateGraph(AgentState)

# 1. Add all the functions as nodes
workflow.add_node("start_job", start_job)
workflow.add_node("triage_document", triage_document)
workflow.add_node("map_summarize_chunks", map_summarize_chunks)
workflow.add_node("check_accuracy", check_accuracy)
workflow.add_node("map_escalate_chunks", map_escalate_chunks)
workflow.add_node("reduce_compile_summary", reduce_compile_summary)
workflow.add_node("store_for_rag", store_for_rag)
workflow.add_node("calculate_carbon", calculate_carbon)
workflow.add_node("run_carbon_router", run_carbon_router)

# 2. Define the *edges* (the path)
workflow.set_entry_point("start_job")

# Conditional routing after start
workflow.add_conditional_edges(
    "start_job",
    route_start_job,
    {
        "eco_mode": "run_carbon_router",
        "standard_mode": "triage_document"
    }
)

workflow.add_edge("triage_document", "map_summarize_chunks")
workflow.add_edge("map_summarize_chunks", "check_accuracy")

# 3. Define the "Conditional" Edge (The "Agentic" part)
workflow.add_conditional_edges(
    "check_accuracy",
    should_rerun,
    {
        "escalate": "map_escalate_chunks",
        "compile": "reduce_compile_summary"
    }
)

# 4. Define the rest of the path
# If we escalate, we check accuracy again on the new chunk
workflow.add_edge("map_escalate_chunks", "check_accuracy") 

# Final linear path
workflow.add_edge("reduce_compile_summary", "store_for_rag")
workflow.add_edge("store_for_rag", "calculate_carbon")
workflow.add_edge("calculate_carbon", END)
workflow.add_edge("run_carbon_router", END)

# 5. Compile the graph
agentic_graph = workflow.compile()

log.info("Agentic Graph compiled successfully.")