from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from agents import workflow
from langchain_core.messages import HumanMessage
import json
import os
import hashlib
from langgraph.checkpoint.memory import MemorySaver

app = FastAPI(title="AI Gym Automation API", description="LangGraph Gym System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage (no DB required)
memory_checkpointer = MemorySaver()
users_store = {}       # email -> password_hash
feedback_store = []    # list of feedback dicts
thread_store = {}      # thread_id -> list of messages

class ChatRequest(BaseModel):
    prompt: str
    thread_id: str = "default-thread"

@app.get("/history")
def get_history(email: str = ""):
    """Returns list of threads for the given user."""
    threads_data = []
    for t_id, msgs in thread_store.items():
        if email and not t_id.startswith(email.replace("@", "").replace(".", "")):
            continue
        title = "New Workout Plan"
        if msgs:
            first = msgs[0].get("content", "") if isinstance(msgs[0], dict) else getattr(msgs[0], "content", "")
            if first:
                title = first[:30] + ("..." if len(first) > 30 else "")
        threads_data.append({"id": t_id, "title": title})
    return {"threads": threads_data}

@app.get("/history/{thread_id}")
async def get_thread_history(thread_id: str):
    """Fetches messages for a specific conversation."""
    msgs = thread_store.get(thread_id, [])
    res = []
    for m in msgs:
        if isinstance(m, dict):
            res.append(m)
        else:
            role = "user" if isinstance(m, HumanMessage) else "assistant"
            res.append({"role": role, "content": m.content})
    return {"messages": res}

@app.post("/stream")
async def stream_chat_endpoint(request: ChatRequest):
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")
        
    def event_generator():
        agent_app = workflow.compile(checkpointer=memory_checkpointer)
        
        initial_state = {"messages": [HumanMessage(content=request.prompt)]}
        config = {"configurable": {"thread_id": request.thread_id}}
        
        # Track messages for history
        if request.thread_id not in thread_store:
            thread_store[request.thread_id] = []
        thread_store[request.thread_id].append({"role": "user", "content": request.prompt})
        
        try:
            current_node = ""
            full_response = ""
            for chunk, metadata in agent_app.stream(initial_state, config, stream_mode="messages"):
                node_name = metadata.get("langgraph_node", "")
                
                if node_name and node_name != current_node:
                    current_node = node_name
                    yield f"event: agent_change\ndata: {node_name}\n\n"

                if getattr(chunk, "content", None) and not isinstance(chunk, HumanMessage):
                    full_response += chunk.content
                    yield f"data: {json.dumps({'token': chunk.content})}\n\n"
                    
            # Store assistant response
            if full_response:
                thread_store[request.thread_id].append({"role": "assistant", "content": full_response})
            
            yield "event: end\ndata: \n\n"
        except Exception as e:
            import traceback
            error_details = traceback.format_exc().replace('\n', ' ')
            yield f"event: error\ndata: {error_details}\n\n"
            print(traceback.format_exc())

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/admin/dashboard-stats")
def get_dashboard_stats():
    """Returns metrics based on in-memory thread history."""
    customer_metrics = {}
    for t_id, msgs in thread_store.items():
        # Extract email from thread_id
        parts = t_id.rsplit('-', 1)
        email = parts[0] if len(parts) > 1 else t_id
        if "@" not in email and "gmail" not in email:
            continue
            
        has_workout = False
        has_diet = False
        is_approved = False
        
        for m in msgs:
            text = (m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")).lower()
            if "routine" in text or "workout" in text or "exercise" in text:
                has_workout = True
            if "diet" in text or "meal" in text or "nutrition" in text:
                has_diet = True
            if "to-do list" in text or "approved" in text or "finalize" in text:
                is_approved = True

        if email not in customer_metrics:
            customer_metrics[email] = {
                "customer": email,
                "coach_plans": 0,
                "nutritionist_plans": 0,
                "manager_approvals": 0,
                "total_threads": 0
            }
        
        customer_metrics[email]["total_threads"] += 1
        if has_workout: customer_metrics[email]["coach_plans"] += 1
        if has_diet: customer_metrics[email]["nutritionist_plans"] += 1
        if is_approved: customer_metrics[email]["manager_approvals"] += 1
                
    return {"metrics": list(customer_metrics.values())}

class FeedbackRequest(BaseModel):
    name: str
    phone: str
    comment: str
    thread_id: str

@app.post("/feedback")
def submit_feedback(request: FeedbackRequest):
    feedback_store.append({
        "name": request.name,
        "phone": request.phone,
        "comment": request.comment,
        "thread_id": request.thread_id
    })
    return {"status": "success"}

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

class AuthRequest(BaseModel):
    email: str
    password: str

@app.post("/register")
def register(request: AuthRequest):
    if request.email in users_store:
        raise HTTPException(status_code=400, detail="User already exists")
    users_store[request.email] = hash_password(request.password)
    return {"status": "success", "email": request.email}

@app.post("/login")
def login(request: AuthRequest):
    stored_hash = users_store.get(request.email)
    if not stored_hash or stored_hash != hash_password(request.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"status": "success", "email": request.email}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
