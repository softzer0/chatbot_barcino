import json
from collections import Counter
from datetime import datetime, timedelta

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
from django.db.models import F
from django.utils import timezone
from nltk import ngrams

from .redis_init import redis_conn
from chatbot.utils import DateTimeEncoder
from .genie import Genie


contact_keywords = 'kontaktiram kontaktiraj kontakt kontaktirajte kontaktira'\
                   ' zboruvam zboruvaj zboruvanje zboruvajte zboruva'\
                   ' tipkam tipkaj tipkanje tipkajte tipka'\
                   ' pisuvam pisuvaj pisuvanje pisuvajte pisuva' \
                   ' pišuvam pišuvaj pišuvanje pišuvajte pišuva'\
                   ' prasam prasaj prasanje prasajte prasa'\
                   ' prašam prašaj prašanje prašajte praša'\
                   ' контактирам контактирај контакт контактирајте контактира'\
                   ' зборувам зборувај зборување зборувајте зборува'\
                   ' типкам типкај типкање типкајте типка'\
                   ' пишувам пишувај пишување пишувајте пишува'\
                   ' прашам прашај прашање прашајте праша'
agent_keywords = 'agenta agent agenti agentom'\
                 ' operator operatori operatorot'\
                 ' covek covekot čovek čovekot'\
                 ' агента агент агенти агентом'\
                 ' оператор оператори операторот'\
                 ' човек човекот'

def calculate_trigram_similarity(message, keywords):
    keywords_list = keywords.split(' ')
    scores = []
    for keyword in keywords_list:
        trigrams_message = Counter(ngrams(message, 3))
        trigrams_keyword = Counter(ngrams(keyword, 3))

        intersection = trigrams_message & trigrams_keyword
        union = trigrams_message | trigrams_keyword

        if sum(union.values()) != 0:
            scores.append(sum(intersection.values()) / sum(union.values()))
    return max(scores)


MESSAGE_LIMIT_PER_IP = 5
TIME_LIMIT_PER_IP = timedelta(hours=1)
GLOBAL_MESSAGE_LIMIT_PER_MINUTE = 25

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        from .models import Document
        self.genie = await database_sync_to_async(Genie)(Document.objects.all())
        self.session = None
        self.group_name = None
        await self.accept()
        await self.handle_exceeded_msg_limit()

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

    @staticmethod
    async def get_global_msg_limit(update=True):
        current_minute = datetime.now().replace(second=0, microsecond=0)
        key = f"messages:{current_minute}"
        count = redis_conn.get(key)

        # If the key doesn't exist, initialize it
        if count is None:
            if update:
                redis_conn.set(key, 1)
                # Set the key to expire after 1 minute
                redis_conn.expireat(key, current_minute + timedelta(minutes=1))
            return False, 0

        count = int(count)
        # If the count exceeds the limit
        if count >= GLOBAL_MESSAGE_LIMIT_PER_MINUTE:
            ttl = redis_conn.ttl(key)
            return True, ttl

        # Otherwise, increment the count if update is True
        if update:
            redis_conn.incr(key)
        return False, 0

    @database_sync_to_async
    def get_message_limit(self):
        from .models import UserIP, ChatMessage
        user_ip, created = UserIP.objects.get_or_create(ip_address=self.scope['client_ip'])
        message_count = 0
        remaining_secs = 0
        if not created:
            one_hour_ago = timezone.now() - TIME_LIMIT_PER_IP
            message_count = ChatMessage.objects.filter(
                session__in=user_ip.chat_sessions.all(),
                session__is_human_intercepted=False,
                session__agent_requested=False,
                created_at__gte=one_hour_ago
            ).count()
            if user_ip.latest_message_time:
                remaining_secs = max(0, int((user_ip.latest_message_time + TIME_LIMIT_PER_IP - timezone.now()).total_seconds()))
        return message_count, user_ip, remaining_secs

    @database_sync_to_async
    def update_last_message_time(self, user_ip):
        user_ip.latest_message_time = timezone.now()
        user_ip.save()

    async def handle_exceeded_msg_limit(self, message_count=None, user_ip=None, remaining_secs=None, update_time=False):
        if not user_ip:
            message_count, user_ip, remaining_secs = await self.get_message_limit()
        is_exceeded = False
        if message_count >= MESSAGE_LIMIT_PER_IP:
            is_exceeded = True
            if update_time:
                await self.update_last_message_time(user_ip)
        global_limit = False
        if not is_exceeded:
            is_exceeded, remaining_secs = await self.get_global_msg_limit(update_time)
            if is_exceeded:
                global_limit = True
        if is_exceeded:
            await self.send(text_data=json.dumps({'exceeded_limit': True, 'remaining_secs': remaining_secs, 'global_limit': global_limit}))
        return is_exceeded, message_count, user_ip, remaining_secs

    async def receive(self, text_data=None, bytes_data=None):
        from .models import ChatSession
        text_data_json = json.loads(text_data)
        command = text_data_json['command']

        if command == 'send_message':
            message_count, user_ip, remaining_secs = await self.get_message_limit()

            # Create session on the first message
            if self.session is None:
                if not self.scope['session'].session_key:
                    await database_sync_to_async(self.scope['session'].save)()
                self.session = await database_sync_to_async(ChatSession.objects.create)(sid=self.scope['session'].session_key, user_ip=user_ip)

                self.group_name = self.scope['session'].session_key
                await self.channel_layer.group_add(self.group_name, self.channel_name)

            message = text_data_json['message'][:100]
            if not self.session.is_human_intercepted and not self.session.agent_requested:
                if calculate_trigram_similarity(message, contact_keywords) > 0.05 and\
                   calculate_trigram_similarity(message, agent_keywords) > 0.05:
                    # If the user has requested to contact an agent, set agent_requested to True
                    await self.set_agent_requested()
                    await self.send(text_data=json.dumps({'agent_requested': True}))
                else:
                    is_exceeded_msg_limit = (await self.handle_exceeded_msg_limit(message_count, user_ip, remaining_secs, True))[0]
                    if not is_exceeded_msg_limit:
                        response = await self.genie.ask(message)
                        imgs = await self.genie.find_imgs(response)
                        await self.store_message(self.session, message, response)
                        await self.send(text_data=json.dumps({
                            'message': response.split("Answer to the visitor:\n")[1],
                            'exceeded_limit': message_count + 1 == MESSAGE_LIMIT_PER_IP,
                            'remaining_secs': remaining_secs,
                            'imgs': imgs
                        }))
            if self.session.is_human_intercepted or self.session.agent_requested:
                await self.store_message(self.session, message, None)

        elif command == 'submit_info':
            await self.save_visitor_info(text_data_json['data'])

    @database_sync_to_async
    def set_agent_requested(self):
        self.session.refresh_from_db()
        self.session.agent_requested = True
        self.session.save()

    @database_sync_to_async
    def save_visitor_info(self, data):
        from .models import VisitorInfo
        self.session.refresh_from_db()
        self.session.info_provided = True
        self.session.save()

        # Convert date strings to datetime.date objects
        if 'date_from' in data and isinstance(data['date_from'], str):
            data['date_from'] = datetime.strptime(data['date_from'], '%Y-%m-%d').date()
        if 'date_until' in data and isinstance(data['date_until'], str):
            data['date_until'] = datetime.strptime(data['date_until'], '%Y-%m-%d').date()

        # Create or update VisitorInfo
        visitor_info, created = VisitorInfo.objects.update_or_create(
            session=self.session,
            defaults=data
        )

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

    async def file_uploaded(self, event):
        await self.send(text_data=json.dumps(event))


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
        return list(ChatSession.objects.all().annotate(last_message_text=F('last_message__message')).order_by('pk').values())

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

    async def file_uploaded(self, event):
        await self.send(text_data=json.dumps(event))
