import os
import pickle
import re
import traceback

import requests
from bs4 import BeautifulSoup
from channels.db import database_sync_to_async
from langchain.callbacks import get_openai_callback
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
# from langchain.retrievers import SVMRetriever
from langchain.schema import HumanMessage
from langchain.vectorstores import Chroma
from langchain.embeddings import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter # , SpacyTextSplitter
from langchain.chat_models import ChatOpenAI
from langchain.chains import RetrievalQA, create_qa_with_structure_chain, StuffDocumentsChain
from langchain import PromptTemplate

from django.conf import settings

from main.schema import CustomResponseSchema

PRE_SPLITTED_TEXTS_PATH = settings.MEDIA_ROOT / 'documents/texts.pkl'
TEXTS_PATH = settings.MEDIA_ROOT / 'documents/texts_splitted.pkl'


class Genie:
    genie = None

    def __init__(self, documents):
        if Genie.genie is None:
            self.documents = documents
            self.texts = self.load_texts()
            vectordb = self.embeddings(self.texts)
            prompt_messages = [
                SystemMessagePromptTemplate.from_template_file(settings.MEDIA_ROOT / 'prompt.txt', []),
                HumanMessage(content="Answer question using the following context"),
                HumanMessagePromptTemplate.from_template("{context}"),
                HumanMessagePromptTemplate.from_template("Question: {question}"),
            ]
            chain_prompt = ChatPromptTemplate(messages=prompt_messages)
            llm = ChatOpenAI(temperature=0, model="gpt-3.5-turbo-0613")
            qa_chain = create_qa_with_structure_chain(llm, CustomResponseSchema, output_parser="pydantic", prompt=chain_prompt)
            document_prompt = PromptTemplate(
                input_variables=["page_content"],
                template="{page_content}"
            )
            final_qa_chain = StuffDocumentsChain(
                llm_chain=qa_chain,
                document_variable_name="context",
                document_prompt=document_prompt,
            )
            Genie.genie = RetrievalQA(
                retriever=vectordb.as_retriever(), combine_documents_chain=final_qa_chain
            )

    def load_texts(self):
        if os.path.exists(TEXTS_PATH):
            with open(TEXTS_PATH, 'rb') as f:
                return pickle.load(f)
        else:
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=1600, chunk_overlap=350, separators=['\n', '\.'])
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
        vectordb.persist()
        return vectordb

    @database_sync_to_async
    def replace_links(self, resp):
        from .models import LINK_PLACEHOLDER, LINK_REGEX, Link
        link_ids = [int(id) for id in re.findall(LINK_REGEX, resp.answer)]
        links = Link.objects.filter(id__in=link_ids)
        for link in links:
            resp.answer = resp.answer.replace(LINK_PLACEHOLDER % link.pk, link.url)
        return resp

    @database_sync_to_async
    def find_imgs(self, lst):
        from main.models import LINK_REGEX, Link
        with open(PRE_SPLITTED_TEXTS_PATH, 'rb') as f:
            texts = pickle.load(f)

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
            try:
                resp = self.genie.run(query)
            except Exception as e:
                print(f"Exception occurred: {e}")
                traceback.print_exc()  # This prints the stack trace
                resp = CustomResponseSchema(
                    residencies=[],
                    answer="Dogodila se greška. Molimo pokušajte ponovo.",
                )
            print(cb)
            return await self.replace_links(resp), cb.total_tokens
