# import system libraries
import os

# import environment loading library
from dotenv import load_dotenv

# import IBMGen library 
from genai.model import Credentials
from genai.schemas import GenerateParams 
from genai.extensions.langchain import LangChainInterface

# import LangChain library
from langchain.chains import RetrievalQA
from langchain.vectorstores import Chroma
from langchain.document_loaders import PDFMinerLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings.sentence_transformer import SentenceTransformerEmbeddings

# initialize variables
pdf_folder_path = './data'
db_folder_path = './db'
model_id = 'meta-llama/llama-2-13b-chat-beam'
db = None

# get GenAI credentials
def get_genai_creds():
    load_dotenv(".env")
    api_key = os.getenv("GENAI_KEY", None)
    api_url = os.getenv("GENAI_API", None)
    if api_key is None or api_url is None:
        print("Either api_key or api_url is None. Please make sure your credentials are correct.")
    creds = Credentials(api_key, api_url)
    return creds

# define embedding function
def initEmbedFunc():
    embedding_function = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")
    return embedding_function

# populate chroma db
def generateDB():
    docs = []
    for root, dirs, files in os.walk(pdf_folder_path):
        for file in files:
            if file.endswith(".pdf"):
                print(f'Reading File: {file}')
                
                # read PDF
                loader = PDFMinerLoader(os.path.join(root, file))
                documents = loader.load()

                # load the document and split it into chunks
                text_splitter = RecursiveCharacterTextSplitter(
                                    chunk_size=1000, 
                                    chunk_overlap=200, 
                                    separators=["\n"]
                )
                temp = text_splitter.split_documents(documents)
                
                # append to docs
                docs += temp

    # create the open-source embedding function
    embedding_function = initEmbedFunc()

    # save to disk
    db = Chroma.from_documents(docs, embedding_function, persist_directory=db_folder_path)
    
    return db

# generate response
def generateResponse(query, qa):
    generated_text = qa(query)
    answer = generated_text['result']
    return answer     

# *** START HERE ***

if [f for f in os.listdir(db_folder_path) if not f.startswith('.')] == []:
    print("Chroma DB is empty. Generating indexes...")
    
    # generate chroma db
    db = generateDB()
else:
    print("Chroma DB is not empty. Using existing indexes!")

    # create the open-source embedding function
    embedding_function = initEmbedFunc()

    # load from disk
    db = Chroma(persist_directory=db_folder_path, embedding_function=embedding_function)

# get credentials
creds = get_genai_creds()

# generate LLM params
params = GenerateParams(
            decoding_method='greedy', 
            min_new_tokens=1,
            max_new_tokens=200,
            stream=False,
            repetition_penalty=1.2)

# create a langchain interface to use with retrieved content
langchain_model = LangChainInterface(model=model_id, params=params, credentials=creds)

# create retrieval QA chain
# create retrieval QA
qa = RetrievalQA.from_chain_type(
        llm=langchain_model,
        chain_type='stuff',
        retriever=db.as_retriever(search_type='similarity', search_kwargs={'k': 2}),
        return_source_documents=True
)

# *** FASTAPI CODE ***
from fastapi import FastAPI
# import uvicorn

app = FastAPI(title='OpenPages QuikBot')

@app.get('/')
def hello_world():
    return "Hello World!"

@app.get('/test/{value}')
def test(value: str):
    return 'Here is the query string passed: %s' % value

@app.post('/qa')
def respond(question: str):
    query = question
    print('Here is the query: %s' % query)
    if (query is not None and len(query.strip()) > 0):
        response = generateResponse(query, qa)
    else:
        response = "Invalid question! Please rephrase your question."
    print(f'Here is the response: {response}')
    data = {
        'answer' : response
    }
    return data

# if __name__ == '__main__':
#     uvicorn.run('app:app', host='0.0.0.0', port=8000, reload=True)