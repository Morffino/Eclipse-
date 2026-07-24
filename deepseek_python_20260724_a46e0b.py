from datetime import datetime
from typing import List, Optional
import json

class Ticket:
    def __init__(self, channel_id: int, user_id: int, user_name: str, topic: str):
        self.channel_id = channel_id
        self.user_id = user_id
        self.user_name = user_name
        self.topic = topic
        self.status = 'open'
        self.created_at = datetime.now()
        self.closing_time = datetime.now()
        self.messages = []
        self.staff_members = []
        self.extended = False
    
    def to_dict(self):
        return {
            'channel_id': self.channel_id,
            'user_id': self.user_id,
            'user_name': self.user_name,
            'topic': self.topic,
            'status': self.status,
            'created_at': self.created_at.isoformat(),
            'closing_time': self.closing_time.isoformat(),
            'messages': self.messages,
            'staff_members': self.staff_members,
            'extended': self.extended
        }
    
    @classmethod
    def from_dict(cls, data):
        ticket = cls(
            data['channel_id'],
            data['user_id'],
            data['user_name'],
            data['topic']
        )
        ticket.status = data['status']
        ticket.created_at = datetime.fromisoformat(data['created_at'])
        ticket.closing_time = datetime.fromisoformat(data['closing_time'])
        ticket.messages = data.get('messages', [])
        ticket.staff_members = data.get('staff_members', [])
        ticket.extended = data.get('extended', False)
        return ticket