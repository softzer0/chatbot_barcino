import os
import pickle
import re

from channels.db import database_sync_to_async
from langchain.callbacks import get_openai_callback
from langchain.vectorstores import Chroma
from langchain.embeddings import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chat_models import ChatOpenAI
from langchain.chains import RetrievalQA
from langchain import PromptTemplate

from django.conf import settings


class Genie:
    vectordb = None
    sales_prompt = None

    def __init__(self, documents):
        self.documents = documents
        if Genie.vectordb is None:
            self.texts = self.load_texts()
            Genie.vectordb = self.embeddings(self.texts)
        if Genie.sales_prompt is None:
            sales_template = open(os.path.join(settings.MEDIA_ROOT, 'prompt.txt'), 'r').read()
            self.sales_prompt = PromptTemplate(
                template=sales_template, input_variables=["context", "question"]
            )
        self.genie = RetrievalQA.from_chain_type(
            llm=ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0),
            chain_type="stuff",
            retriever=Genie.vectordb.as_retriever(),
            return_source_documents=False,
            chain_type_kwargs={"prompt": self.sales_prompt},
        )

    def load_texts(self):
        texts_path = os.path.join(settings.MEDIA_ROOT, 'documents/texts.pkl')
        if os.path.exists(texts_path):
            with open(texts_path, 'rb') as f:
                return pickle.load(f)
        else:
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, separators=['\n\n', '\n'])
            texts = []
            for document in self.documents:
                texts.extend(text_splitter.split_documents(document.preprocess()))
            with open(texts_path, 'wb') as f:
                pickle.dump(texts, f)
            return texts

    @staticmethod
    def embeddings(texts):
        embeddings = OpenAIEmbeddings()
        vectordb = Chroma.from_documents(texts, embeddings, persist_directory=os.path.join(settings.MEDIA_ROOT, 'chroma'))
        return vectordb

    @database_sync_to_async
    def replace_links(self, resp):
        from .models import LINK_PLACEHOLDER, LINK_REGEX, Link
        link_ids = [int(id) for id in re.findall(LINK_REGEX, resp)]
        links = Link.objects.filter(id__in=link_ids)
        for link in links:
            resp = resp.replace(LINK_PLACEHOLDER % link.pk, link.url)
        return resp

    async def ask(self, query: str):
        with get_openai_callback() as cb:
            resp = self.genie.run(query)
            print(cb)
            return await self.replace_links(resp)
