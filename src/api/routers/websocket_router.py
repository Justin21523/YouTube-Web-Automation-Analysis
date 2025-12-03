# src/api/routers/websocket_router.py
"""
WebSocket Router - Real-time communication endpoints
Provides WebSocket connections for live task updates and notifications
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Set, Optional, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


# ============================================================================
# Connection Manager
# ============================================================================

class ConnectionManager:
    """Manages WebSocket connections and broadcasts"""

    def __init__(self):
        # All active connections
        self.active_connections: Dict[str, WebSocket] = {}
        # Connections subscribed to specific channels
        self.channel_subscriptions: Dict[str, Set[str]] = {
            "tasks": set(),
            "notifications": set(),
            "system": set(),
        }
        # Connection metadata
        self.connection_info: Dict[str, Dict[str, Any]] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept a new WebSocket connection"""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.connection_info[client_id] = {
            "connected_at": datetime.utcnow().isoformat(),
            "subscriptions": [],
        }
        logger.info(f"WebSocket connected: {client_id}")

    def disconnect(self, client_id: str):
        """Remove a WebSocket connection"""
        if client_id in self.active_connections:
            del self.active_connections[client_id]

        # Remove from all channel subscriptions
        for channel in self.channel_subscriptions.values():
            channel.discard(client_id)

        if client_id in self.connection_info:
            del self.connection_info[client_id]

        logger.info(f"WebSocket disconnected: {client_id}")

    def subscribe(self, client_id: str, channel: str):
        """Subscribe a client to a channel"""
        if channel in self.channel_subscriptions:
            self.channel_subscriptions[channel].add(client_id)
            if client_id in self.connection_info:
                if channel not in self.connection_info[client_id]["subscriptions"]:
                    self.connection_info[client_id]["subscriptions"].append(channel)
            logger.debug(f"Client {client_id} subscribed to {channel}")

    def unsubscribe(self, client_id: str, channel: str):
        """Unsubscribe a client from a channel"""
        if channel in self.channel_subscriptions:
            self.channel_subscriptions[channel].discard(client_id)
            if client_id in self.connection_info:
                if channel in self.connection_info[client_id]["subscriptions"]:
                    self.connection_info[client_id]["subscriptions"].remove(channel)
            logger.debug(f"Client {client_id} unsubscribed from {channel}")

    async def send_personal(self, client_id: str, message: dict):
        """Send a message to a specific client"""
        if client_id in self.active_connections:
            websocket = self.active_connections[client_id]
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to {client_id}: {e}")
                self.disconnect(client_id)

    async def broadcast(self, message: dict, channel: Optional[str] = None):
        """Broadcast a message to all clients or a specific channel"""
        if channel:
            # Send to channel subscribers only
            clients = self.channel_subscriptions.get(channel, set())
        else:
            # Send to all connected clients
            clients = set(self.active_connections.keys())

        disconnected = []
        for client_id in clients:
            if client_id in self.active_connections:
                try:
                    await self.active_connections[client_id].send_json(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to {client_id}: {e}")
                    disconnected.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected:
            self.disconnect(client_id)

    def get_stats(self) -> dict:
        """Get connection statistics"""
        return {
            "total_connections": len(self.active_connections),
            "channels": {
                channel: len(clients)
                for channel, clients in self.channel_subscriptions.items()
            },
            "connections": list(self.connection_info.keys()),
        }


# Global connection manager instance
manager = ConnectionManager()


# ============================================================================
# WebSocket Message Types
# ============================================================================

class WSMessage(BaseModel):
    type: str
    channel: Optional[str] = None
    data: Optional[dict] = None


# ============================================================================
# WebSocket Endpoints
# ============================================================================

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: Optional[str] = Query(None),
):
    """
    Main WebSocket endpoint for real-time communication

    Message format:
    {
        "type": "subscribe" | "unsubscribe" | "ping" | "message",
        "channel": "tasks" | "notifications" | "system",
        "data": {...}
    }
    """
    # Generate client ID if not provided
    if not client_id:
        client_id = f"client_{datetime.utcnow().timestamp()}"

    await manager.connect(websocket, client_id)

    # Send welcome message
    await manager.send_personal(client_id, {
        "type": "connected",
        "client_id": client_id,
        "message": "Connected to WebSocket server",
        "available_channels": list(manager.channel_subscriptions.keys()),
    })

    try:
        while True:
            # Receive message
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                msg_type = message.get("type", "")
                channel = message.get("channel")
                msg_data = message.get("data", {})

                if msg_type == "subscribe":
                    if channel:
                        manager.subscribe(client_id, channel)
                        await manager.send_personal(client_id, {
                            "type": "subscribed",
                            "channel": channel,
                        })

                elif msg_type == "unsubscribe":
                    if channel:
                        manager.unsubscribe(client_id, channel)
                        await manager.send_personal(client_id, {
                            "type": "unsubscribed",
                            "channel": channel,
                        })

                elif msg_type == "ping":
                    await manager.send_personal(client_id, {
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat(),
                    })

                elif msg_type == "message":
                    # Echo message back for now
                    await manager.send_personal(client_id, {
                        "type": "message_received",
                        "data": msg_data,
                    })

                else:
                    await manager.send_personal(client_id, {
                        "type": "error",
                        "message": f"Unknown message type: {msg_type}",
                    })

            except json.JSONDecodeError:
                await manager.send_personal(client_id, {
                    "type": "error",
                    "message": "Invalid JSON format",
                })

    except WebSocketDisconnect:
        manager.disconnect(client_id)


@router.websocket("/ws/tasks")
async def tasks_websocket(
    websocket: WebSocket,
    client_id: Optional[str] = Query(None),
):
    """
    Dedicated WebSocket endpoint for task updates
    Automatically subscribes to the 'tasks' channel
    """
    if not client_id:
        client_id = f"tasks_{datetime.utcnow().timestamp()}"

    await manager.connect(websocket, client_id)
    manager.subscribe(client_id, "tasks")

    # Send current task status
    await send_task_status_update(client_id)

    try:
        while True:
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                msg_type = message.get("type", "")

                if msg_type == "ping":
                    await manager.send_personal(client_id, {
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat(),
                    })

                elif msg_type == "refresh":
                    # Send updated task status
                    await send_task_status_update(client_id)

                elif msg_type == "subscribe_task":
                    # Subscribe to a specific task's updates
                    task_id = message.get("task_id")
                    if task_id:
                        # Store task subscription
                        await manager.send_personal(client_id, {
                            "type": "subscribed_task",
                            "task_id": task_id,
                        })

            except json.JSONDecodeError:
                await manager.send_personal(client_id, {
                    "type": "error",
                    "message": "Invalid JSON",
                })

    except WebSocketDisconnect:
        manager.disconnect(client_id)


# ============================================================================
# Helper Functions for Broadcasting
# ============================================================================

async def send_task_status_update(client_id: str):
    """Send current task status to a specific client"""
    try:
        from src.infrastructure.tasks.celery_app import celery_app

        # Get active tasks
        inspect = celery_app.control.inspect()
        active = inspect.active() or {}
        reserved = inspect.reserved() or {}

        # Flatten tasks
        active_tasks = []
        for worker, tasks in active.items():
            for task in tasks:
                active_tasks.append({
                    "id": task.get("id"),
                    "name": task.get("name"),
                    "worker": worker,
                    "status": "running",
                    "time_start": task.get("time_start"),
                })

        reserved_tasks = []
        for worker, tasks in reserved.items():
            for task in tasks:
                reserved_tasks.append({
                    "id": task.get("id"),
                    "name": task.get("name"),
                    "worker": worker,
                    "status": "reserved",
                })

        await manager.send_personal(client_id, {
            "type": "task_status",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "active": active_tasks,
                "reserved": reserved_tasks,
                "total_active": len(active_tasks),
                "total_reserved": len(reserved_tasks),
            }
        })

    except Exception as e:
        logger.error(f"Error getting task status: {e}")
        await manager.send_personal(client_id, {
            "type": "task_status",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "active": [],
                "reserved": [],
                "error": str(e),
            }
        })


async def broadcast_task_event(event_type: str, task_data: dict):
    """Broadcast a task event to all task subscribers"""
    await manager.broadcast({
        "type": f"task_{event_type}",
        "timestamp": datetime.utcnow().isoformat(),
        "data": task_data,
    }, channel="tasks")


async def broadcast_notification(
    title: str,
    message: str,
    level: str = "info",
    data: Optional[dict] = None
):
    """Broadcast a notification to all notification subscribers"""
    await manager.broadcast({
        "type": "notification",
        "timestamp": datetime.utcnow().isoformat(),
        "title": title,
        "message": message,
        "level": level,
        "data": data or {},
    }, channel="notifications")


async def broadcast_system_event(event_type: str, data: dict):
    """Broadcast a system event to all system subscribers"""
    await manager.broadcast({
        "type": f"system_{event_type}",
        "timestamp": datetime.utcnow().isoformat(),
        "data": data,
    }, channel="system")


# ============================================================================
# REST Endpoints for WebSocket Management
# ============================================================================

@router.get("/ws/stats")
async def get_websocket_stats():
    """Get WebSocket connection statistics"""
    return manager.get_stats()


@router.post("/ws/broadcast")
async def broadcast_message(
    message: str,
    channel: Optional[str] = None,
    level: str = "info",
):
    """
    Broadcast a message to WebSocket clients
    Used for server-side notifications
    """
    await manager.broadcast({
        "type": "broadcast",
        "timestamp": datetime.utcnow().isoformat(),
        "message": message,
        "level": level,
    }, channel=channel)

    return {
        "success": True,
        "channel": channel or "all",
        "recipients": len(manager.channel_subscriptions.get(channel, set()))
        if channel else len(manager.active_connections),
    }


# ============================================================================
# Background Task Status Broadcaster
# ============================================================================

class TaskStatusBroadcaster:
    """Background service that periodically broadcasts task status"""

    def __init__(self, interval: int = 5):
        self.interval = interval
        self.running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the broadcaster"""
        if self.running:
            return

        self.running = True
        self._task = asyncio.create_task(self._broadcast_loop())
        logger.info("Task status broadcaster started")

    async def stop(self):
        """Stop the broadcaster"""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Task status broadcaster stopped")

    async def _broadcast_loop(self):
        """Main broadcast loop"""
        while self.running:
            try:
                # Only broadcast if there are subscribers
                if manager.channel_subscriptions.get("tasks"):
                    await self._broadcast_task_status()

                await asyncio.sleep(self.interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in broadcast loop: {e}")
                await asyncio.sleep(self.interval)

    async def _broadcast_task_status(self):
        """Broadcast current task status to all task subscribers"""
        try:
            from src.infrastructure.tasks.celery_app import celery_app

            inspect = celery_app.control.inspect()
            active = inspect.active() or {}
            reserved = inspect.reserved() or {}

            # Count tasks
            active_count = sum(len(tasks) for tasks in active.values())
            reserved_count = sum(len(tasks) for tasks in reserved.values())

            # Build task list
            tasks = []
            for worker, worker_tasks in active.items():
                for task in worker_tasks:
                    tasks.append({
                        "id": task.get("id"),
                        "name": task.get("name", "").split(".")[-1],
                        "worker": worker,
                        "status": "running",
                        "started": task.get("time_start"),
                    })

            for worker, worker_tasks in reserved.items():
                for task in worker_tasks:
                    tasks.append({
                        "id": task.get("id"),
                        "name": task.get("name", "").split(".")[-1],
                        "worker": worker,
                        "status": "pending",
                    })

            await manager.broadcast({
                "type": "task_update",
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "active_count": active_count,
                    "reserved_count": reserved_count,
                    "tasks": tasks,
                }
            }, channel="tasks")

        except Exception as e:
            logger.error(f"Error broadcasting task status: {e}")


# Global broadcaster instance
task_broadcaster = TaskStatusBroadcaster()


# Lifecycle hooks
async def start_broadcaster():
    """Start the task status broadcaster"""
    await task_broadcaster.start()


async def stop_broadcaster():
    """Stop the task status broadcaster"""
    await task_broadcaster.stop()
