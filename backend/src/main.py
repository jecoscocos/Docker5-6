from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from email_service import send_email_smtp, check_emails_imap, check_emails_pop3
import json
from typing import List, Dict
from datetime import datetime

app = FastAPI()

# Добавляем CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000", "http://todo-frontend:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],  # Разрешаем все HTTP методы
    allow_headers=["*"],  # Разрешаем все заголовки
)

# Эндпоинт для проверки работоспособности API
@app.get("/api/health")
async def health_check():
    try:
        conn = get_db_connection()
        if conn is None:
            return {"status": "error", "message": "Database connection failed"}
        conn.close()
        return {"status": "ok", "message": "API is running"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Класс для хранения активных WebSocket соединений
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict):
        for connection in self.active_connections:
            await connection.send_json(message)

manager = ConnectionManager()

# Функция для преобразования объекта datetime в строку для JSON
def datetime_converter(o):
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(f"Object of type {type(o)} is not JSON serializable")

# Функция для преобразования RealDictRow к JSON-сериализуемому dict
def prepare_task_for_json(task):
    # Преобразуем RealDictRow в обычный dict
    task_dict = dict(task)
    # Преобразуем datetime в строку
    if 'created_at' in task_dict and isinstance(task_dict['created_at'], datetime):
        task_dict['created_at'] = task_dict['created_at'].isoformat()
    return task_dict

# Модель задачи
class Task(BaseModel):
    title: str
    description: str = None
    status: str = "pending"

# Модель для отправки email
class EmailRequest(BaseModel):
    recipient_email: str
    subject: str
    message_body: str
    task_id: int

# Подключение к базе данных
def get_db_connection():
    host = os.getenv('POSTGRES_HOST', 'todo-db')
    database = os.getenv('POSTGRES_DB', 'tododb')
    user = os.getenv('POSTGRES_USER', 'admin')
    password = os.getenv('POSTGRES_PASSWORD', 'admin123')
    
    print(f"Connecting to database: host={host}, database={database}, user={user}")
    
    try:
        conn = psycopg2.connect(
            host=host,
            database=database,
            user=user,
            password=password
        )
        print("Database connection successful")
        return conn
    except Exception as e:
        print(f"Database connection error: {str(e)}")
        # В случае ошибки вернем None
        return None

# WebSocket эндпоинт
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Просто ждем сообщение, но ничего с ним не делаем
            # Основная логика будет в HTTP эндпоинтах
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/tasks")
async def get_tasks():
    try:
        conn = get_db_connection()
        if conn is None:
            return {"error": "Database connection failed"}
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM tasks")
        tasks = cur.fetchall()
        cur.close()
        conn.close()
        return tasks
    except Exception as e:
        print(f"Error getting tasks: {str(e)}")
        return {"error": str(e)}

@app.post("/tasks")
async def create_task(task: Task):
    try:
        conn = get_db_connection()
        if conn is None:
            return {"error": "Database connection failed"}
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "INSERT INTO tasks (title, description, status) VALUES (%s, %s, %s) RETURNING *",
            (task.title, task.description, task.status)
        )
        new_task = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        # Отправляем уведомление всем клиентам через WebSocket
        # Преобразуем задачу в JSON-сериализуемый формат
        json_task = prepare_task_for_json(new_task)
        await manager.broadcast({
            "action": "create",
            "task": json_task
        })
        
        return new_task
    except Exception as e:
        print(f"Error creating task: {str(e)}")
        return {"error": str(e)}

@app.get("/tasks/{task_id}")
async def get_task(task_id: int):
    try:
        conn = get_db_connection()
        if conn is None:
            return {"error": "Database connection failed"}
            
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
        task = cur.fetchone()
        cur.close()
        conn.close()
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return task
    except Exception as e:
        print(f"Error getting task: {str(e)}")
        return {"error": str(e)}

@app.put("/tasks/{task_id}")
async def update_task(task_id: int, task: Task):
    try:
        conn = get_db_connection()
        if conn is None:
            return {"error": "Database connection failed"}
            
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "UPDATE tasks SET title = %s, description = %s, status = %s WHERE id = %s RETURNING *",
            (task.title, task.description, task.status, task_id)
        )
        updated_task = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if updated_task is None:
            raise HTTPException(status_code=404, detail="Task not found")
            
        # Отправляем уведомление всем клиентам через WebSocket
        # Преобразуем задачу в JSON-сериализуемый формат
        json_task = prepare_task_for_json(updated_task)
        await manager.broadcast({
            "action": "update",
            "task": json_task
        })
        
        return updated_task
    except Exception as e:
        print(f"Error updating task: {str(e)}")
        return {"error": str(e)}

@app.delete("/tasks/{task_id}")
async def delete_task(task_id: int):
    try:
        conn = get_db_connection()
        if conn is None:
            return {"error": "Database connection failed"}
            
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("DELETE FROM tasks WHERE id = %s RETURNING *", (task_id,))
        deleted_task = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if deleted_task is None:
            raise HTTPException(status_code=404, detail="Task not found")
            
        # Отправляем уведомление всем клиентам через WebSocket
        # Преобразуем задачу в JSON-сериализуемый формат
        json_task = prepare_task_for_json(deleted_task)
        await manager.broadcast({
            "action": "delete",
            "task": json_task
        })
        
        return {"message": "Task deleted successfully"}
    except Exception as e:
        print(f"Error deleting task: {str(e)}")
        return {"error": str(e)}

# Новые эндпоинты для работы с электронной почтой

@app.post("/email/send")
async def send_email(email_request: EmailRequest):
    """
    Отправка email для определенной задачи
    """
    try:
        # Получаем информацию о задаче
        conn = get_db_connection()
        if conn is None:
            return {"success": False, "message": "Database connection failed"}
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM tasks WHERE id = %s", (email_request.task_id,))
        task = cur.fetchone()
        cur.close()
        conn.close()
        
        if task is None:
            return {"success": False, "message": "Task not found"}
        
        # Отправляем email
        result = await send_email_smtp(
            email_request.recipient_email,
            email_request.subject,
            email_request.message_body,
            task
        )
        
        return result
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return {"success": False, "message": f"Error sending email: {str(e)}"}

@app.get("/email/check/imap")
async def check_imap_emails():
    """
    Проверка email через IMAP протокол
    """
    try:
        result = check_emails_imap()
        return result
    except Exception as e:
        print(f"Error checking IMAP emails: {str(e)}")
        return {"success": False, "message": f"Error checking IMAP emails: {str(e)}"}

@app.get("/email/check/pop3")
async def check_pop3_emails():
    """
    Проверка email через POP3 протокол
    """
    try:
        result = check_emails_pop3()
        return result
    except Exception as e:
        print(f"Error checking POP3 emails: {str(e)}")
        return {"success": False, "message": f"Error checking POP3 emails: {str(e)}"} 