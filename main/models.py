import re

from django.contrib.auth.models import User
from django.db import models
from langchain.document_loaders import (
    PyPDFLoader,
    UnstructuredHTMLLoader,
    UnstructuredFileLoader,
    UnstructuredWordDocumentLoader,
    DataFrameLoader,
)
import pandas as pd


URL_PATTERN = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
LINK_PLACEHOLDER = '<LINK[%i]>'
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
        'csv': DataFrameLoader,
        'xlsx': DataFrameLoader,
        'pdf': PyPDFLoader,
        'html': UnstructuredHTMLLoader,
        'txt': UnstructuredFileLoader,
        'docx': UnstructuredWordDocumentLoader,
    }

    def load(self, mode='elements', strategy='fast'):
        loader = self.LOADER_MAP[self.doc_type]
        if loader == DataFrameLoader:
            if self.doc_type == 'csv':
                df = pd.read_csv(self.doc_file.path)
            else:  # xlsx
                df = pd.read_excel(self.doc_file.path)
            return loader(df, page_content_column=df.iloc[0].str.len().idxmax()).load()
        elif self.doc_type != 'pdf':
            return loader(self.doc_file.path, mode=mode, strategy=strategy).load()
        else:
            return loader(self.doc_file.path).load()

    def _process_links(self, content):
        links = URL_PATTERN.findall(content)
        for link in links:
            l_obj = Link.objects.create(document=self, url=link)
            placeholder = LINK_PLACEHOLDER % l_obj.pk
            content = content.replace(link, placeholder)
        return content

    def preprocess(self):
        documents = self.load()
        for doc in documents:
            doc.page_content = "Page content is: " + self._process_links(doc.page_content) + '\n'
            link_p = []
            for key, content in doc.metadata.items():
                if isinstance(content, str):
                    link_p.append(self._process_links(content))
                else:
                    doc.page_content += f'Column "{key}" is {doc.metadata[key]}\n'
            doc.page_content = 'Link placeholders: [' + ', '.join(link_p) + '] -> ' + doc.page_content + '\n\n'
        return documents


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
