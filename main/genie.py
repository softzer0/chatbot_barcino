from langchain.vectorstores import Chroma
from langchain.embeddings import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chat_models import ChatOpenAI
from langchain.chains import RetrievalQA
from langchain import PromptTemplate


class Genie:
    def __init__(self, documents):
        self.texts = self.text_split(documents)
        self.vectordb = self.embeddings(self.texts)
        sales_template = """You're a Barcino travel sales bot

        Language: Macedonian

        {context}

        Question: {question}"""
        SALES_PROMPT = PromptTemplate(
            template=sales_template, input_variables=["context", "question"]
        )
        self.genie = RetrievalQA.from_chain_type(
            llm=ChatOpenAI(model_name="gpt-3.5-turbo"),
            chain_type="stuff",
            retriever=self.vectordb.as_retriever(),
            return_source_documents=False,
            chain_type_kwargs={"prompt": SALES_PROMPT},
        )

    @staticmethod
    def text_split(documents):
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
        texts = []
        for document in documents:
            loader = document.get_loader()
            texts.extend(text_splitter.split_documents(loader.load()))
        return texts

    @staticmethod
    def embeddings(texts):
        embeddings = OpenAIEmbeddings()
        vectordb = Chroma.from_documents(texts, embeddings)
        return vectordb

    def ask(self, query):
        return self.genie.run(query)
