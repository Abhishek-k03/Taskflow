# taskflow/api/websocket.py

from fastapi import WebSocket, WebSocketDisconnect
from typing import Set, Dict
import json
import asyncio
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for real-time updates"""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.subscriptions: Dict[str, Set[WebSocket]] = {}  # task_id -> connections
    
    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection"""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection"""
        self.active_connections.discard(websocket)
        
        # Remove from all subscriptions
        for task_id in list(self.subscriptions.keys()):
            self.subscriptions[task_id].discard(websocket)
            if not self.subscriptions[task_id]:
                del self.subscriptions[task_id]
        
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    def subscribe(self, websocket: WebSocket, task_id: str):
        """Subscribe connection to specific task updates"""
        if task_id not in self.subscriptions:
            self.subscriptions[task_id] = set()
        self.subscriptions[task_id].add(websocket)
        logger.debug(f"WebSocket subscribed to task {task_id}")
    
    def unsubscribe(self, websocket: WebSocket, task_id: str):
        """Unsubscribe connection from task updates"""
        if task_id in self.subscriptions:
            self.subscriptions[task_id].discard(websocket)
            if not self.subscriptions[task_id]:
                del self.subscriptions[task_id]
        logger.debug(f"WebSocket unsubscribed from task {task_id}")
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send message to specific connection"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
            self.disconnect(websocket)
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connections"""
        disconnected = []
        
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to connection: {e}")
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)
    
    async def send_to_task_subscribers(self, task_id: str, message: dict):
        """Send message to all connections subscribed to a specific task"""
        if task_id not in self.subscriptions:
            return
        
        disconnected = []
        
        for connection in self.subscriptions[task_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to subscriber: {e}")
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)
    
    def get_stats(self) -> dict:
        """Get connection statistics"""
        return {
            'total_connections': len(self.active_connections),
            'active_subscriptions': len(self.subscriptions),
            'subscribed_tasks': list(self.subscriptions.keys()),
        }


# Global connection manager
manager = ConnectionManager()


async def task_event_handler(event_type: str, task):
    """Handle task events and broadcast to WebSocket clients
    
    This is called by WorkerPool when task events occur
    """
    message = {
        'type': event_type,
        'task': task.to_dict(),
        'timestamp': task.completed_at.isoformat() if task.completed_at else task.created_at.isoformat(),
    }
    
    # Send to task-specific subscribers
    await manager.send_to_task_subscribers(task.task_id, message)
    
    # Also broadcast to all connections for dashboard
    await manager.broadcast(message)


async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint handler"""
    await manager.connect(websocket)
    
    try:
        while True:
            # Receive messages from client
            data = await websocket.receive_json()
            
            # Handle different message types
            message_type = data.get('type')
            
            if message_type == 'subscribe':
                # Subscribe to specific task updates
                task_id = data.get('task_id')
                if task_id:
                    manager.subscribe(websocket, task_id)
                    await manager.send_personal_message(
                        {'type': 'subscribed', 'task_id': task_id},
                        websocket
                    )
            
            elif message_type == 'unsubscribe':
                # Unsubscribe from task updates
                task_id = data.get('task_id')
                if task_id:
                    manager.unsubscribe(websocket, task_id)
                    await manager.send_personal_message(
                        {'type': 'unsubscribed', 'task_id': task_id},
                        websocket
                    )
            
            elif message_type == 'ping':
                # Keep-alive ping
                await manager.send_personal_message(
                    {'type': 'pong'},
                    websocket
                )
    
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        manager.disconnect(websocket)