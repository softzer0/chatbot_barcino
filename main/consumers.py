import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.db.models import F

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

        if not self.session.is_human_intercepted:
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

        # Update the session's last_message field
        session.last_message = chat_message
        session.save()


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

        elif command == 'delete_session':
            session_id = text_data_json['session_id']
            await self.delete_session(session_id)
            await self.send(text_data=json.dumps({
                'command': 'deleted_session',
                'session_id': session_id
            }))

        elif command == 'rename_session':
            session_id = text_data_json['session_id']
            new_name = text_data_json['new_name']
            session = await self.rename_session(session_id, new_name)
            await self.send(text_data=json.dumps({
                'command': 'renamed_session',
                'session_id': session_id,
                'last_message_text': await self.get_last_message(session),
                'new_name': new_name
            }))

        elif command == 'intercept_session':
            session_id = text_data_json['session_id']
            await self.intercept_session(session_id)
            username = await self.get_username()
            await self.send(text_data=json.dumps({
                'command': 'intercepted_session',
                'session_id': session_id,
                'intercepted_by': username
            }))

    @database_sync_to_async
    def get_username(self):
        return self.scope['user'].username

    @database_sync_to_async
    def intercept_session(self, session_id):
        from .models import ChatSession
        session = ChatSession.objects.get(id=session_id)
        session.is_human_intercepted = True
        session.human_agent = self.scope['user']
        session.save()

    @database_sync_to_async
    def get_last_message(self, session):
        return session.last_message.message

    @database_sync_to_async
    def delete_session(self, session_id):
        from .models import ChatSession
        ChatSession.objects.get(id=session_id).delete()

    @database_sync_to_async
    def rename_session(self, session_id, new_name):
        from .models import ChatSession
        session = ChatSession.objects.get(id=session_id)
        session.name = new_name
        session.save()
        return session

    @database_sync_to_async
    def get_sessions(self):
        from .models import ChatSession
        return list(ChatSession.objects.all().annotate(last_message_text=F('last_message__message')).values())

    @database_sync_to_async
    def get_messages(self, session_id):
        from .models import ChatMessage
        return list(ChatMessage.objects.filter(session_id=session_id).values())

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event, cls=DateTimeEncoder))

    async def chat_session(self, event):
        await self.send(text_data=json.dumps(event, cls=DateTimeEncoder))
