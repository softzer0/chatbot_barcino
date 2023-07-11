import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from .genie import Genie


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        from .models import Document
        self.genie = await database_sync_to_async(Genie)(Document.objects.all())
        await self.accept()

    async def disconnect(self, close_code):
        pass

    async def receive(self, text_data=None, bytes_data=None):
        text_data_json = json.loads(text_data)
        message = text_data_json['message']
        response = self.genie.ask(message)
        await self.store_message(message, response)
        await self.send(text_data=json.dumps({
            'message': response
        }))

    @staticmethod
    async def store_message(message, response):
        from .models import ChatMessage
        chat_message = await database_sync_to_async(ChatMessage)(message=message, response=response)
        await database_sync_to_async(chat_message.save)()
