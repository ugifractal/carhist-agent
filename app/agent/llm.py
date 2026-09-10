from app.config import get_groq_api_key

# from langchain_google_genai import ChatGoogleGenerativeAI  # GEMINI — temporarily disabled
from langchain_groq import ChatGroq  # GROQ — free tier (openai/gpt-oss-120b)


def get_llm():
    return ChatGroq(
        model="openai/gpt-oss-120b",
        api_key=get_groq_api_key(),
        temperature=0,
    )
