import json
import os
from typing import Dict, List
from models.ticket import Ticket
from datetime import datetime

class Database:
    def __init__(self, file_path: str = 'data/ticket_history.json'):
        self.file_path = file_path
        self.history: Dict[int, Dict] = {}
        self.load()
    
    def load(self):
        """Загрузка истории из файла"""
        try:
            if os.path.exists(self.file_path):
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for ticket_id, info in data.items():
                        self.history[int(ticket_id)] = info
        except Exception as e:
            print(f"Ошибка загрузки базы данных: {e}")
    
    def save(self):
        """Сохранение истории в файл"""
        try:
            # Создаем директорию если её нет
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения базы данных: {e}")
    
    def add_ticket(self, ticket: Ticket):
        """Добавление тикета в историю"""
        self.history[ticket.channel_id] = {
            'user_id': ticket.user_id,
            'user_name': ticket.user_name,
            'topic': ticket.topic,
            'created_at': ticket.created_at.isoformat(),
            'closed_at': None,
            'closed_by': None,
            'close_reason': None,
            'staff_members': [],
            'messages': []
        }
        self.save()
    
    def close_ticket(self, channel_id: int, closed_by: str, reason: str, messages: List[str], staff: List[int]):
        """Закрытие тикета в истории"""
        if channel_id in self.history:
            self.history[channel_id]['closed_at'] = datetime.now().isoformat()
            self.history[channel_id]['closed_by'] = closed_by
            self.history[channel_id]['close_reason'] = reason
            self.history[channel_id]['staff_members'] = staff
            self.history[channel_id]['messages'] = messages
            self.save()
    
    def get_ticket(self, channel_id: int) -> Dict:
        """Получение информации о тикете"""
        return self.history.get(channel_id)
    
    def get_all_tickets(self) -> Dict:
        """Получение всех тикетов"""
        return self.history
    
    def get_stats(self) -> Dict:
        """Получение статистики"""
        total = len(self.history)
        closed = sum(1 for t in self.history.values() if t['closed_at'] is not None)
        open_tickets = total - closed
        
        # Статистика по темам
        topics = {}
        for ticket in self.history.values():
            topic = ticket['topic']
            topics[topic] = topics.get(topic, 0) + 1
        
        return {
            'total': total,
            'open': open_tickets,
            'closed': closed,
            'topics': topics
        }