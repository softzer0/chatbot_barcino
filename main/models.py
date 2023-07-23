import re

from django.contrib.auth.models import User
from django.db import models
from langchain.document_loaders import (
    UnstructuredCSVLoader,
    UnstructuredExcelLoader,
    PyPDFLoader,
    UnstructuredHTMLLoader,
    TextLoader,
    UnstructuredWordDocumentLoader,
)
from langchain.docstore.document import Document as LCDocument


URL_PATTERN = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
LINK_PLACEHOLDER = 'link://%i'
LINK_REGEX = re.escape(LINK_PLACEHOLDER).replace('%i', r'(\d+)')


class Document(models.Model):
    DOC_TYPE_CHOICES = [
        ('csv', 'CSV'),
        ('pdf', 'PDF'),
        ('xlsx', 'Excel'),
        ('html', 'HTML'),
        ('txt', 'Text'),
        ('docx', 'Word'),
    ]
    name = models.CharField(max_length=255)
    doc_file = models.FileField(upload_to='documents/')
    doc_type = models.CharField(max_length=5, choices=DOC_TYPE_CHOICES)

    LOADER_MAP = {
        'csv': UnstructuredCSVLoader,
        'xlsx': UnstructuredExcelLoader,
        'pdf': PyPDFLoader,
        'html': UnstructuredHTMLLoader,
        'txt': TextLoader,
        'docx': UnstructuredWordDocumentLoader,
    }

    def get_loader(self, mode='elements', strategy='fast'):
        if self.doc_type == 'pdf':
            return self.LOADER_MAP['pdf'](self.doc_file.path)
        elif self.doc_type == 'txt':
            return self.LOADER_MAP['txt'](self.doc_file.path, autodetect_encoding=True)
        else:
            return self.LOADER_MAP[self.doc_type](self.doc_file.path, mode=mode, strategy=strategy)

    def preprocess_text(self):
        loader = self.get_loader()
        document = loader.load()
        docs = []
        if len(document) == 1:
            for txt in document[0].page_content.split('\n'):
                docs.append(LCDocument(page_content=txt + '\n', metadata=document[0].metadata))
        else:
            docs = document
        for doc in docs:
            url_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
            links = url_pattern.findall(doc.page_content)
            for link in links:
                l_obj = Link.objects.create(document=self, url=link)
                placeholder = LINK_PLACEHOLDER % l_obj.pk
                doc.page_content = doc.page_content.replace(link, placeholder)
        return docs

class Link(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE)
    url = models.URLField(max_length=2000)
    img_links = models.TextField(null=True, blank=True)


class UserIP(models.Model):
    ip_address = models.GenericIPAddressField()

class ChatSession(models.Model):
    user_ip = models.ForeignKey(UserIP, on_delete=models.CASCADE, related_name='chat_sessions')
    sid = models.CharField(max_length=50)
    name = models.CharField(max_length=255, null=True, blank=True)
    is_terminated = models.BooleanField(default=False)
    info_provided = models.BooleanField(default=False)
    last_message = models.OneToOneField('ChatMessage', related_name='+', on_delete=models.SET_NULL, null=True, blank=True)
    is_human_intercepted = models.BooleanField(default=False)
    human_agent = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    agent_requested = models.BooleanField(default=False)

    def to_dict(self):
        return {
            'id': self.id,
            'sid': self.sid,
            'name': self.name,
            'is_terminated': self.is_terminated,
            'info_provided': self.info_provided,
            'last_message_text': self.last_message.message if self.last_message else None,
            'is_human_intercepted': self.is_human_intercepted,
            'human_agent': self.human_agent.id if self.human_agent else None,
        }

class ChatMessage(models.Model):
    session = models.ForeignKey(ChatSession, related_name='messages', on_delete=models.CASCADE)
    message = models.TextField(null=True, blank=True)
    response = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def to_dict(self):
        return {
            'id': self.id,
            'message': self.message,
            'response': self.response,
            'created_at': self.created_at
        }

class VisitorInfo(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True)
    contact_phone = models.CharField(max_length=20, null=True, blank=True)
    arrangement = models.CharField(max_length=255, null=True, blank=True)
    adults = models.PositiveIntegerField(null=True, blank=True)
    children = models.PositiveIntegerField(null=True, blank=True)
    budget = models.FloatField(null=True, blank=True)
    date_from = models.DateField(null=True, blank=True)
    date_until = models.DateField(null=True, blank=True)
    session = models.OneToOneField(ChatSession, on_delete=models.CASCADE, related_name='visitor_info')

    def to_dict(self):
        return {
            'name': self.name,
            'contact_phone': self.contact_phone,
            'arrangement': self.arrangement,
            'adults': self.adults,
            'children': self.children,
            'budget': self.budget,
            'date_from': self.date_from.strftime('%Y-%m-%d') if self.date_from else None,
            'date_until': self.date_until.strftime('%Y-%m-%d') if self.date_until else None
        }

class FileAttachment(models.Model):
    file = models.FileField(upload_to='attachments/')
    name = models.CharField(max_length=255)

