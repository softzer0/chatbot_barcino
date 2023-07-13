import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from chatbot.utils import DateTimeEncoder
from .genie import Genie


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        from .models import Document
        self.genie = await database_sync_to_async(Genie)(Document.objects.all())
        self.session = None
        await self.accept()

    async def receive(self, text_data=None, bytes_data=None):
        from .models import ChatSession
        text_data_json = json.loads(text_data)
        message = text_data_json['message']

        # Create session on the first message
        if self.session is None:
            # force session to save and set the session key
            await database_sync_to_async(self.scope["session"].save)()
            self.session = await database_sync_to_async(ChatSession.objects.create)(sid=self.scope['session'].session_key)

        response = self.genie.ask(message)
        await self.store_message(self.session, message, response)
        await self.send(text_data=json.dumps({
            'message': response
        }))

    @staticmethod
    @database_sync_to_async
    def store_message(session, message, response):
        from .models import ChatMessage
        chat_message = ChatMessage(session=session, message=message, response=response)
        chat_message.save()


class PanelConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = 'panel'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        text_data_json = json.loads(text_data)
        command = text_data_json['command']

        if command == 'fetch_sessions':
            sessions = await self.get_sessions()
            await self.send(text_data=json.dumps({
                'command': 'fetch_sessions',
                'sessions': sessions
            }))
        elif command == 'fetch_messages':
            session_id = text_data_json['session_id']
            messages = await self.get_messages(session_id)
            await self.send(text_data=json.dumps({
                'command': 'fetch_messages',
                'messages': messages
            }, cls=DateTimeEncoder))

    @database_sync_to_async
    def get_sessions(self):
        from .models import ChatSession
        return list(ChatSession.objects.all().values())

    @database_sync_to_async
    def get_messages(self, session_id):
        from .models import ChatMessage
        return list(ChatMessage.objects.filter(session_id=session_id).values())

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event, cls=DateTimeEncoder))

    async def chat_session(self, event):
        await self.send(text_data=json.dumps(event, cls=DateTimeEncoder))
