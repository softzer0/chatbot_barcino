import os
import pickle
import re

import requests
from bs4 import BeautifulSoup
from channels.db import database_sync_to_async
from langchain.callbacks import get_openai_callback
from langchain.vectorstores import Chroma
from langchain.embeddings import OpenAIEmbeddings
from langchain.text_splitter import SpacyTextSplitter, RecursiveCharacterTextSplitter
from langchain.chat_models import ChatOpenAI
from langchain.chains import RetrievalQA
from langchain import PromptTemplate

from django.conf import settings


PRE_SPLITTED_TEXTS_PATH = os.path.join(settings.MEDIA_ROOT, 'documents/texts.pkl')
TEXTS_PATH = os.path.join(settings.MEDIA_ROOT, 'documents/texts_splitted.pkl')


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
        if os.path.exists(TEXTS_PATH):
            with open(TEXTS_PATH, 'rb') as f:
                return pickle.load(f)
        else:
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=1550, chunk_overlap=450, separators=['\n', '\.', ','])
            pre_splitted_texts = []
            texts = []
            for document in self.documents:
                processed_txt = document.preprocess_text()
                pre_splitted_texts.extend(processed_txt)
                texts.extend(text_splitter.split_documents(processed_txt))
            with open(PRE_SPLITTED_TEXTS_PATH, 'wb') as f:
                pickle.dump(pre_splitted_texts, f)
            with open(TEXTS_PATH, 'wb') as f:
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

    @database_sync_to_async
    def find_imgs(self, resp):
        from main.models import LINK_REGEX, Link
        with open(PRE_SPLITTED_TEXTS_PATH, 'rb') as f:
            texts = pickle.load(f)

        try:
            resp = resp.split("List of names of residencies in answer:\n")[1]
            if not resp.split('\n')[0]:
                resp = resp.split('\n')[1]
            else:
                resp = resp.split('\n')[0]
            lst = resp.split(', ')
        except:
            return
        imgs = []
        link_ids = {}

        for item in lst:
            item = item.strip()
            if not item:
                continue
            match_before = False
            prev_line = ''
            for chunk in texts:
                # Loop through each line in page content
                for line in chunk.page_content.split('\n'):
                    # Case insensitive search
                    if item.lower() in line.lower() or match_before:
                        # Find link IDs
                        link_id = re.search(LINK_REGEX, line)
                        if not link_id:
                            link_id = re.search(LINK_REGEX, prev_line)
                        if not link_id:
                            if not match_before:
                                match_before = True
                            else:
                                match_before = False
                            prev_line = line
                            continue
                        link_id = int(link_id.group(1))
                        if link_id in link_ids:
                            for i, img in enumerate(imgs):
                                if img['name'] == link_ids[link_id]:
                                    imgs.append({'name': link_ids[link_id] + ', ' + item, 'link': img['link'], 'images': img['images']})
                                    del imgs[i]
                                    break
                            continue
                        try:
                            link = Link.objects.get(id=link_id)
                        except:
                            continue

                        if not link.img_links:
                            response = requests.get(link.url)
                            soup = BeautifulSoup(response.text, 'html.parser')

                            # Look for div elements with "gallery" in class
                            gallery_elements = soup.find_all(lambda tag: tag.name == 'div' and 'gallery__full-image' in tag.get('class', []))

                            img_links = set()
                            for element in gallery_elements:
                                # Look for img tags within those elements and extract the 'src' attribute
                                for img in element.find_all('img'):
                                    val = img.get('src') or img.get('data-src')
                                    if val:
                                        img_links.add(val)

                            img_links = list(img_links)
                            # Update the Link model
                            link.img_links = ','.join(img_links)
                            link.save()
                            imgs.append({'name': item, 'link': link.url, 'images': img_links})
                        else:
                            imgs.append({'name': item, 'link': link.url, 'images': link.img_links.split(',')})
                        link_ids[link.pk] = item
                        break
                    prev_line = line
                else:
                    continue
                break
        return imgs

    async def ask(self, query: str):
        with get_openai_callback() as cb:
            resp = self.genie.run(query)
            print(cb)
            return await self.replace_links(resp)
