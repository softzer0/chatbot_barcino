import re

from django.contrib.auth.models import User
from django.db import models
from langchain.document_loaders import (
    UnstructuredCSVLoader,
    UnstructuredExcelLoader,
    PyPDFLoader,
    UnstructuredHTMLLoader,
    UnstructuredFileLoader,
    UnstructuredWordDocumentLoader,
)


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
        'txt': UnstructuredFileLoader,
        'docx': UnstructuredWordDocumentLoader,
    }

    def get_loader(self, mode='elements', strategy='fast'):
        if self.doc_type != 'pdf':
            return self.LOADER_MAP[self.doc_type](self.doc_file.path, mode=mode, strategy=strategy)
        else:
            return self.LOADER_MAP[self.doc_type](self.doc_file.path)

    def preprocess_text(self):
        loader = self.get_loader()
        document = loader.load()
        for doc in document:
            url_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
            links = url_pattern.findall(doc.page_content)
            for link in links:
                l_obj = Link.objects.create(document=self, url=link)
                placeholder = LINK_PLACEHOLDER % l_obj.pk
                doc.page_content = doc.page_content.replace(link, placeholder)
        return document


class Link(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE)
    url = models.URLField(max_length=2000)


class ChatSession(models.Model):
    sid = models.CharField(max_length=50)
    name = models.CharField(max_length=255, null=True, blank=True)
    is_terminated = models.BooleanField(default=False)
    info_provided = models.BooleanField(default=False)
    last_message = models.OneToOneField('ChatMessage', related_name='+', on_delete=models.SET_NULL, null=True, blank=True)
    is_human_intercepted = models.BooleanField(default=False)
    human_agent = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

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
    session = models.OneToOneField(ChatSession, on_delete=models.CASCADE, related_name='visitor_info')

    def to_dict(self):
        return {
            'name': self.name,
            'contact_phone': self.contact_phone,
            'arrangement': self.arrangement,
        }
