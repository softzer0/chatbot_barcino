import json

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
from django.db.models import F

from chatbot.utils import DateTimeEncoder
from .genie import Genie


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        from .models import Document
        self.genie = await database_sync_to_async(Genie)(Document.objects.all())
        self.session = None
        self.group_name = None
        await self.accept()

    async def disconnect(self, close_code):
        await self.close_session()
        if self.group_name:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    @database_sync_to_async
    def close_session(self):
        if self.session:
            self.session.refresh_from_db()
            self.session.is_terminated = True
            self.session.save()

    async def receive(self, text_data=None, bytes_data=None):
        from .models import ChatSession
        text_data_json = json.loads(text_data)
        command = text_data_json['command']

        if command == 'send_message':
            # Create session on the first message
            if self.session is None:
                if not self.scope['session'].session_key:
                    await database_sync_to_async(self.scope['session'].save)()
                self.session = await database_sync_to_async(ChatSession.objects.create)(sid=self.scope['session'].session_key)

                self.group_name = self.scope['session'].session_key
                await self.channel_layer.group_add(self.group_name, self.channel_name)

            message = text_data_json['message']
            if not self.session.is_human_intercepted:
                response = await self.genie.ask(message)
                imgs = await self.genie.find_imgs(response)
                await self.store_message(self.session, message, response)
                await self.send(text_data=json.dumps({
                    'message': response.split("Answer to the visitor:\n")[1],
                    'imgs': imgs
                }))
            else:
                await self.store_message(self.session, message, None)

        elif command == 'submit_info':
            name = text_data_json['name']
            contact_phone = text_data_json['contact_phone']
            arrangement = text_data_json['arrangement']
            await self.save_visitor_info(name, contact_phone, arrangement)

    @database_sync_to_async
    def save_visitor_info(self, name, contact_phone, arrangement):
        from .models import VisitorInfo
        self.session.refresh_from_db()
        self.session.info_provided = True
        self.session.save()
        # Check if VisitorInfo already exists for this session
        visitor_info, created = VisitorInfo.objects.get_or_create(
            session=self.session,
            defaults={
                'name': name,
                'contact_phone': contact_phone,
                'arrangement': arrangement,
            }
        )

        # If VisitorInfo already exists, update it
        if not created:
            visitor_info.name = name
            visitor_info.contact_phone = contact_phone
            visitor_info.arrangement = arrangement
            visitor_info.save()

        # After storing the visitor info, broadcast it to the 'panel' group
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            'panel',
            {
                'type': 'update_visitor_info',
                'command': 'visitor_info',
                'session_id': self.session.pk,
                'info': visitor_info.to_dict(),
            },
        )

    @staticmethod
    @database_sync_to_async
    def store_message(session, message, response):
        from .models import ChatMessage
        chat_message = ChatMessage(session=session, message=message, response=response)
        chat_message.save()

        # Update the session's last_message field
        session.refresh_from_db()
        session.last_message = chat_message
        session.save()

    async def intercepted_message(self, event):
        # Send message to WebSocket
        self.session.is_human_intercepted = True
        await self.send(text_data=json.dumps({
            'message': event['message'],
            'human_intercepted': True
        }))


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
            messages, can_intercept = await self.get_messages(session_id)
            await self.send(text_data=json.dumps({
                'command': 'fetch_messages',
                'messages': messages,
                'can_intercept': can_intercept
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
            interception_successful = await self.intercept_session(session_id)
            if interception_successful:
                chat_message = await self.send_message(session_id, text_data_json['message'])
                is_interceptor = await self.check_is_interceptor(session_id)
                await self.send(text_data=json.dumps({
                    'command': 'intercepted_session',
                    'session_id': session_id,
                    'is_interceptor': is_interceptor,
                    'message': chat_message.to_dict()
                }, cls=DateTimeEncoder))
                await self.channel_layer.group_send(await self.get_session_sid_by_id(session_id), {
                    'type': 'intercepted_message',
                    'message': chat_message.response
                })
            else:
                await self.send(text_data=json.dumps({
                    'command': 'interception_failed',
                    'session_id': session_id,
                    'reason': 'Session has already been intercepted'
                }))

        elif command == 'fetch_visitor_info':
            session_id = text_data_json['session_id']
            visitor_info = await self.fetch_visitor_info(session_id)
            if visitor_info:
                await self.send(text_data=json.dumps({
                    'command': 'visitor_info',
                    'session_id': session_id,
                    'info': visitor_info.to_dict()
                }))

    @database_sync_to_async
    def fetch_visitor_info(self, session_id):
        from .models import VisitorInfo
        return VisitorInfo.objects.filter(session_id=session_id).first()

    @database_sync_to_async
    def check_is_interceptor(self, session_id):
        from .models import ChatSession
        return ChatSession.objects.filter(pk=session_id, human_agent=self.scope['user']).exists()

    @database_sync_to_async
    def get_session_sid_by_id(self, session_id):
        from .models import ChatSession
        return ChatSession.objects.get(pk=session_id).sid

    @database_sync_to_async
    def intercept_session(self, session_id):
        from .models import ChatSession
        session = ChatSession.objects.get(id=session_id)
        # Only allow interception if the session hasn't been intercepted before
        if not session.is_human_intercepted:
            session.is_human_intercepted = True
            session.human_agent = self.scope['user']
            session.save()
            return True
        elif session.human_agent == self.scope['user']:
            return True
        else:
            return False

    @database_sync_to_async
    def send_message(self, session_id, response):
        from .models import ChatMessage
        return ChatMessage.objects.create(session_id=session_id, message=None, response=response)

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
        return list(ChatSession.objects.all().annotate(last_message_text=F('last_message__message')).order_by('info_provided').values())

    @database_sync_to_async
    def get_messages(self, session_id):
        from .models import ChatSession, ChatMessage
        session = ChatSession.objects.get(pk=session_id)
        return list(ChatMessage.objects.filter(session_id=session_id).order_by('pk').values()), \
            not session.is_terminated and (not session.is_human_intercepted or self.scope['user'] == session.human_agent)

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event, cls=DateTimeEncoder))

    async def chat_session(self, event):
        await self.send(text_data=json.dumps(event, cls=DateTimeEncoder))

    async def update_visitor_info(self, event):
        await self.send(text_data=json.dumps(event))
