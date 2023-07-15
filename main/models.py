from django.db import models
from langchain.document_loaders import (
    UnstructuredCSVLoader,
    PyPDFLoader,
    UnstructuredExcelLoader,
    UnstructuredHTMLLoader,
    UnstructuredFileLoader,
    UnstructuredWordDocumentLoader,
)


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
        'pdf': PyPDFLoader,
        'xlsx': UnstructuredExcelLoader,
        'html': UnstructuredHTMLLoader,
        'txt': UnstructuredFileLoader,
        'docx': UnstructuredWordDocumentLoader,
    }

    def get_loader(self, mode='elements', strategy='fast'):
        if self.doc_type != 'pdf':
            return self.LOADER_MAP[self.doc_type](self.doc_file.path, mode=mode, strategy=strategy)
        else:
            self.LOADER_MAP[self.doc_type](self.doc_file.path)


class ChatSession(models.Model):
    sid = models.CharField(max_length=50)
    last_message = models.OneToOneField('ChatMessage', related_name='+', on_delete=models.SET_NULL, null=True, blank=True)

class ChatMessage(models.Model):
    session = models.ForeignKey(ChatSession, related_name='messages', on_delete=models.CASCADE)
    message = models.TextField()
    response = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
