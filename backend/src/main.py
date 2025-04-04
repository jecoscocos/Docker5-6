import os
import typing
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
import psycopg2.extras

from email_service import send_email_smtp, check_emails_pop3, check_emails_imap

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://admin:admin123@localhost:5432/tododb')


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)


manager = ConnectionManager()


def get_db_connection():
    """Create a database connection."""
    try:
        conn = psycopg2.connect(
            DATABASE_URL,
            cursor_factory=psycopg2.extras.RealDictCursor
        )
        return conn
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        return None


class Task(BaseModel):
    title: str
    description: str
    status: str


class EmailRequest(BaseModel):
    recipient_email: str
    subject: str
    message_body: str
    task_id: Optional[int] = None


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Message text was: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/tasks")
async def get_tasks():
    """Get all tasks."""
    try:
        conn = get_db_connection()
        if not conn:
            return {"success": False, "message": "Database connection failed"}

        cur = conn.cursor()
        cur.execute('SELECT * FROM tasks ORDER BY id')
        tasks = cur.fetchall()

        cur.close()
        conn.close()

        return tasks
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.post("/tasks")
async def create_task(task: Task):
    """Create a new task."""
    try:
        conn = get_db_connection()
        if not conn:
            return {"success": False, "message": "Database connection failed"}

        cur = conn.cursor()
        cur.execute(
            'INSERT INTO tasks (title, description, status, created_at) VALUES (%s, %s, %s, %s) RETURNING *',
            (task.title, task.description, task.status, datetime.now())
        )
        new_task = cur.fetchone()
        conn.commit()

        cur.close()
        conn.close()

        await manager.broadcast({"action": "create", "task": new_task})
        return new_task
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/tasks/{task_id}")
async def get_task(task_id: int):
    """Get a specific task by ID."""
    try:
        conn = get_db_connection()
        if not conn:
            return {"success": False, "message": "Database connection failed"}

        cur = conn.cursor()
        cur.execute('SELECT * FROM tasks WHERE id = %s', (task_id,))
        task = cur.fetchone()

        cur.close()
        conn.close()

        if task is None:
            return {"success": False, "message": "Task not found"}

        return task
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.put("/tasks/{task_id}")
async def update_task(task_id: int, task: Task):
    """Update a specific task."""
    try:
        conn = get_db_connection()
        if not conn:
            return {"success": False, "message": "Database connection failed"}

        cur = conn.cursor()
        cur.execute(
            'UPDATE tasks SET title = %s, description = %s, status = %s WHERE id = %s RETURNING *',
            (task.title, task.description, task.status, task_id)
        )
        updated_task = cur.fetchone()
        conn.commit()

        cur.close()
        conn.close()

        if updated_task is None:
            return {"success": False, "message": "Task not found"}

        await manager.broadcast({"action": "update", "task": updated_task})
        return updated_task
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.delete("/tasks/{task_id}")
async def delete_task(task_id: int):
    """Delete a specific task."""
    try:
        conn = get_db_connection()
        if not conn:
            return {"success": False, "message": "Database connection failed"}

        cur = conn.cursor()
        cur.execute('DELETE FROM tasks WHERE id = %s RETURNING *', (task_id,))
        deleted_task = cur.fetchone()
        conn.commit()

        cur.close()
        conn.close()

        if deleted_task is None:
            return {"success": False, "message": "Task not found"}

        await manager.broadcast({"action": "delete", "task": deleted_task})
        return {"success": True, "message": "Task deleted successfully"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.post("/email/send")
async def send_email(email_request: EmailRequest):
    """Send an email."""
    try:
        if email_request.task_id:
            conn = get_db_connection()
            if not conn:
                return {"success": False, "message": "Database connection failed"}

            cur = conn.cursor()
            cur.execute('SELECT * FROM tasks WHERE id = %s', (email_request.task_id,))
            task = cur.fetchone()
            cur.close()
            conn.close()

            if task:
                email_request.message_body += f"\n\nTask Details:\nTitle: {task['title']}\nDescription: {task['description']}\nStatus: {task['status']}"

        result = await send_email_smtp(
            email_request.recipient_email,
            email_request.subject,
            email_request.message_body
        )
        return result
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/email/check/pop3")
async def check_pop3_emails():
    """Check emails using POP3."""
    try:
        result = check_emails_pop3()
        return result
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/email/check/imap")
async def check_imap_emails():
    """Check emails using IMAP."""
    try:
        result = check_emails_imap()
        return result
    except Exception as e:
        return {"success": False, "message": str(e)}


# CORS configuration
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
) 