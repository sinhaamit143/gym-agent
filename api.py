from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from agents import workflow
from langchain_core.messages import HumanMessage
import json
import urllib.parse
from contextlib import asynccontextmanager
import sys
import asyncio
import os
import smtplib
from email.message import EmailMessage
import hashlib

# psycopg ConnectionPool internally spawns background asyncio workers.
# On Windows, we must force SelectorEventLoop globally to prevent Proactor crashes.
if sys.platform == "win32" and sys.version_info >= (3, 8):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver

DB_USER = "postgres"
DB_PASS = urllib.parse.quote_plus("admin@123$$%") # Safe URL encoding
DB_HOST = "db.rydduxnckmfpdxjinfvl.supabase.co"
DB_PORT = "5432"
DB_NAME = "postgres"
DB_URI = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}?sslmode=require"

# Global connection pool
pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = ConnectionPool(
        conninfo=DB_URI,
        max_size=20,
        kwargs={"autocommit": True, "prepare_threshold": 0}
    )
    
    # Ensure checkpointer schema is created 
    with pool.connection() as conn:
        saver = PostgresSaver(conn)
        saver.setup()
    
    yield
    pool.close()

app = FastAPI(title="AI Gym Automation API", description="LangGraph Supabase Gym System", lifespan=lifespan)

class ChatRequest(BaseModel):
    prompt: str
    thread_id: str = "default-thread"

@app.get("/history")
def get_history(email: str = ""):
    """Fetches a list of all historical threads backed by Supabase with dynamic titles."""
    try:
        threads_data = []
        with pool.connection() as conn:
            with conn.cursor() as cur:
                if email:
                    cur.execute("SELECT DISTINCT thread_id FROM checkpoints WHERE thread_id LIKE %s ORDER BY thread_id DESC;", (f"{email}-%",))
                else:
                    cur.execute("SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id DESC;")
                
                rows = cur.fetchall()
                
                checkpointer = PostgresSaver(conn)
                for row in rows:
                    t_id = row[0]
                    config = {"configurable": {"thread_id": t_id}}
                    state = checkpointer.get(config)
                    title = "New Workout Plan"
                    if state and "messages" in state.get("channel_values", {}):
                        msgs = state["channel_values"]["messages"]
                        if msgs:
                            first_msg = getattr(msgs[0], "content", "")
                            if first_msg:
                                title = first_msg[:30] + ("..." if len(first_msg) > 30 else "")
                    threads_data.append({"id": t_id, "title": title})
                    
        return {"threads": threads_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/history/{thread_id}")
async def get_thread_history(thread_id: str):
    """Fetches messages for a specific conversation."""
    try:
        checkpointer = PostgresSaver(pool)
        config = {"configurable": {"thread_id": thread_id}}
        
        state = checkpointer.get(config)
        if not state or "messages" not in state["channel_values"]:
            return {"messages": []}
            
        messages = state["channel_values"]["messages"]
        res = []
        for m in messages:
            role = "user" if isinstance(m, HumanMessage) else "assistant"
            # In a real app we might decode which agent sent it, but basic formatting works
            res.append({"role": role, "content": m.content})
            
        return {"messages": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/stream")
async def stream_chat_endpoint(request: ChatRequest):
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")
        
    def event_generator():
        # Instantiate saver using the global pool
        checkpointer = PostgresSaver(pool)
        agent_app = workflow.compile(checkpointer=checkpointer)
        
        initial_state = {"messages": [HumanMessage(content=request.prompt)]}
        config = {"configurable": {"thread_id": request.thread_id}}
        
        try:
            current_node = ""
            for chunk, metadata in agent_app.stream(initial_state, config, stream_mode="messages"):
                node_name = metadata.get("langgraph_node", "")
                
                if node_name and node_name != current_node:
                    current_node = node_name
                    yield f"event: agent_change\ndata: {node_name}\n\n"

                if getattr(chunk, "content", None) and not isinstance(chunk, HumanMessage):
                    yield f"data: {json.dumps({'token': chunk.content})}\n\n"
                    
            yield "event: end\ndata: \n\n"
        except Exception as e:
            import traceback
            error_details = traceback.format_exc().replace('\n', ' ')
            yield f"event: error\ndata: {error_details}\n\n"
            print(traceback.format_exc())

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/admin/dashboard-stats")
def get_dashboard_stats():
    """Generates a dynamic Admin Dashboard report calculating plan creations and approvals per-agent per-customer."""
    try:
        with pool.connection() as conn:
            checkpointer = PostgresSaver(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id DESC;")
                rows = cur.fetchall()
                
                customer_metrics = {}

                for row in rows:
                    t_id = row[0]
                    email_parts = t_id.rsplit('-', 1)
                    email = email_parts[0] if len(email_parts) > 1 else t_id
                    if "@" not in email:
                        continue 

                    config = {"configurable": {"thread_id": t_id}}
                    state = checkpointer.get(config)
                    if not state or "messages" not in state.get("channel_values", {}):
                        continue
                    
                    msgs = state["channel_values"]["messages"]
                    
                    has_workout = False
                    has_diet = False
                    is_approved = False
                    
                    for m in msgs:
                        if getattr(m, "type", "") == "ai":
                            text = getattr(m, 'content', '').lower()
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class EmailRequest(BaseModel):
    email: str
    content: str
    
class FeedbackRequest(BaseModel):
    name: str
    phone: str
    comment: str
    thread_id: str

@app.post("/send-email")
def send_email(request: EmailRequest):
    try:
        BREVO_USER = os.getenv("BREVO_USER", "apikey")
        BREVO_PASS = os.getenv("BREVO_PASS", "placeholder_change_me")
        
        msg = EmailMessage()
        msg.set_content(request.content)
        msg['Subject'] = 'Your Custom AI Gym Plan & Day 1 To-Do List'
        msg['From'] = "fitness@aigym.com"
        msg['To'] = request.email

        with smtplib.SMTP("smtp-relay.brevo.com", 587) as server:
            server.starttls()
            server.login(BREVO_USER, BREVO_PASS)
            server.send_message(msg)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/feedback")
def submit_feedback(request: FeedbackRequest):
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS contact_feedback (
                        id SERIAL PRIMARY KEY,
                        name TEXT,
                        phone TEXT,
                        comment TEXT,
                        thread_id TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("""
                    INSERT INTO contact_feedback (name, phone, comment, thread_id)
                    VALUES (%s, %s, %s, %s)
                """, (request.name, request.phone, request.comment, request.thread_id))
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

class AuthRequest(BaseModel):
    email: str
    password: str

@app.post("/register")
def register(request: AuthRequest):
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS gym_users (
                        id SERIAL PRIMARY KEY,
                        email TEXT UNIQUE,
                        password_hash TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("SELECT id FROM gym_users WHERE email = %s", (request.email,))
                if cur.fetchone():
                    raise HTTPException(status_code=400, detail="User already exists")
                
                cur.execute(
                    "INSERT INTO gym_users (email, password_hash) VALUES (%s, %s)",
                    (request.email, hash_password(request.password))
                )
        return {"status": "success", "email": request.email}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/login")
def login(request: AuthRequest):
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS gym_users (
                        id SERIAL PRIMARY KEY,
                        email TEXT UNIQUE,
                        password_hash TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("SELECT password_hash FROM gym_users WHERE email = %s", (request.email,))
                row = cur.fetchone()
                if not row or row[0] != hash_password(request.password):
                    raise HTTPException(status_code=401, detail="Invalid credentials")
        return {"status": "success", "email": request.email}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
