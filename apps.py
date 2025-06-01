# RMIT Enrolment Advisor Chatbot
# Author: Enhanced for RMIT Student Enrolment Support
# Updated: May 2025

import streamlit as st
import json
import boto3
import os
import re
import requests
from datetime import datetime
from PyPDF2 import PdfReader
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
from bs4 import BeautifulSoup
import urllib.parse

# Load environment variables
load_dotenv()

# === Configuration Labels === #
APP_TITLE = "RMIT Enrolment Advisor"
APP_SUBTITLE = "Your intelligent assistant for RMIT course enrolment and academic guidance"
CHAT_PLACEHOLDER = "Ask me anything about RMIT enrolment, courses, deadlines, or academic policies..."
PROCESSING_MESSAGE = "Processing your question..."
SUCCESS_MESSAGE = "Response generated successfully"
ERROR_MESSAGE = "An error occurred. Please try again."

# === AWS Configuration === #
REGION = os.getenv("AWS_REGION", "us-east-1")
MODEL_ID = os.getenv("MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
IDENTITY_POOL_ID = os.getenv("IDENTITY_POOL_ID")
USER_POOL_ID = os.getenv("USER_POOL_ID")
APP_CLIENT_ID = os.getenv("APP_CLIENT_ID")
USERNAME = os.getenv("AWS_USERNAME")
PASSWORD = os.getenv("AWS_PASSWORD")

# === Knowledge Base Configuration === #
KNOWLEDGE_BASE_DIR = "knowledge_base"
RMIT_ENROLMENT_URL = "https://www.rmit.edu.au/students/my-course/enrolment/enrol-new-student"

# === Helper: Get AWS Credentials === #
def get_credentials(username, password):
    """Authenticate with AWS Cognito and return credentials"""
    try:
        idp_client = boto3.client("cognito-idp", region_name=REGION)
        response = idp_client.initiate_auth(
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": username, "PASSWORD": password},
            ClientId=APP_CLIENT_ID,
        )
        id_token = response["AuthenticationResult"]["IdToken"]

        identity_client = boto3.client("cognito-identity", region_name=REGION)
        identity_response = identity_client.get_id(
            IdentityPoolId=IDENTITY_POOL_ID,
            Logins={f"cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}": id_token},
        )

        creds_response = identity_client.get_credentials_for_identity(
            IdentityId=identity_response["IdentityId"],
            Logins={f"cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}": id_token},
        )

        return creds_response["Credentials"]
    except Exception as e:
        st.error(f"Authentication failed: {str(e)}")
        return None

# === Extract text from PDFs === #
def extract_text_from_pdfs(pdf_paths):
    """Extract text from multiple PDF files"""
    all_text = []
    for pdf_path in pdf_paths:
        try:
            with open(pdf_path, 'rb') as file:
                reader = PdfReader(file)
                pdf_text = []
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        pdf_text.append(text.strip())
                all_text.append({
                    'source': pdf_path,
                    'content': "\n\n".join(pdf_text)
                })
        except Exception as e:
            all_text.append({
                'source': pdf_path,
                'content': f"[Error reading file {pdf_path}: {str(e)}]"
            })
    return all_text

# === Data Cleaning Function === #
def clean_knowledge_data(raw_data):
    """Clean and preprocess knowledge base data"""
    cleaned_data = []
    
    for item in raw_data:
        if isinstance(item, dict):
            # Remove empty values and None
            cleaned_item = {k: v for k, v in item.items() if v is not None and str(v).strip()}
            
            # Clean text content
            for key, value in cleaned_item.items():
                if isinstance(value, str):
                    # Remove excessive whitespace
                    value = re.sub(r'\s+', ' ', value.strip())
                    # Remove special characters that might interfere with processing
                    value = re.sub(r'[^\w\s\-.,!?():]', '', value)
                    # Standardize course codes (e.g., COSC1111, INTE2402)
                    value = re.sub(r'\b([A-Z]{4})(\d{4})\b', r'\1\2', value)
                    cleaned_item[key] = value
            
            if cleaned_item:  # Only add non-empty items
                cleaned_data.append(cleaned_item)
        
        elif isinstance(item, str):
            # Clean string data
            cleaned_text = re.sub(r'\s+', ' ', item.strip())
            cleaned_text = re.sub(r'[^\w\s\-.,!?():]', '', cleaned_text)
            if cleaned_text:
                cleaned_data.append(cleaned_text)
    
    return cleaned_data

# === Prompt Tuning Function === #
def tune_prompt_for_context(base_prompt, user_question, context_type="general"):
    """Enhance prompt based on question type and context"""
    
    # Analyze user question to determine intent
    question_lower = user_question.lower()
    
    # Define prompt enhancements based on question type
    if any(word in question_lower for word in ['enrol', 'enrollment', 'enrolment', 'register']):
        context_enhancement = """
        Focus on enrolment procedures, deadlines, requirements, and step-by-step guidance.
        Provide specific actionable steps and mention relevant deadlines.
        """
    elif any(word in question_lower for word in ['course', 'subject', 'unit']):
        context_enhancement = """
        Focus on course information, prerequisites, descriptions, and academic planning.
        Help with course selection and academic pathway guidance.
        """
    elif any(word in question_lower for word in ['deadline', 'date', 'when']):
        context_enhancement = """
        Emphasize important dates, deadlines, and time-sensitive information.
        Provide specific dates and time frames where available.
        """
    elif any(word in question_lower for word in ['fee', 'cost', 'payment', 'financial']):
        context_enhancement = """
        Focus on financial information, fees, payment options, and financial support.
        Provide clear cost breakdowns and payment deadlines.
        """
    else:
        context_enhancement = """
        Provide comprehensive assistance covering all aspects of RMIT enrolment and academic support.
        """
    
    enhanced_prompt = f"""
{base_prompt}

CONTEXT GUIDANCE:
{context_enhancement}

RESPONSE GUIDELINES:
- Be specific and actionable
- Include relevant links or contact information when helpful
- Use clear, student-friendly language
- Organize information with bullet points or steps when appropriate
- Always verify information is current and accurate

USER QUESTION: {user_question}
"""
    
    return enhanced_prompt

# === Load Knowledge Base === #
@st.cache_data
def load_knowledge_base():
    """Load and process knowledge base from various sources"""
    knowledge_data = []
    
    # Create knowledge base directory if it doesn't exist
    Path(KNOWLEDGE_BASE_DIR).mkdir(exist_ok=True)
    
    # Load JSON files
    json_files = list(Path(KNOWLEDGE_BASE_DIR).glob("*.json"))
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    knowledge_data.extend(data)
                else:
                    knowledge_data.append(data)
        except Exception as e:
            st.warning(f"Could not load {json_file}: {str(e)}")
    
    # Load PDF files
    pdf_files = list(Path(KNOWLEDGE_BASE_DIR).glob("*.pdf"))
    if pdf_files:
        pdf_data = extract_text_from_pdfs(pdf_files)
        knowledge_data.extend(pdf_data)
    
    # Clean the data
    cleaned_data = clean_knowledge_data(knowledge_data)
    
    return cleaned_data

# === Build Enhanced Prompt === #
def build_prompt(user_question, knowledge_base=None):
    """Build enhanced prompt with knowledge base integration"""
    
    # Load knowledge base if not provided
    if knowledge_base is None:
        knowledge_base = load_knowledge_base()
    
    # Format knowledge base content
    knowledge_content = ""
    if knowledge_base:
        knowledge_content = "\n\n### RMIT KNOWLEDGE BASE:\n"
        for i, item in enumerate(knowledge_base):
            if isinstance(item, dict):
                if 'source' in item and 'content' in item:
                    knowledge_content += f"Source: {item['source']}\n{item['content']}\n\n"
                else:
                    knowledge_content += f"Entry {i+1}: {json.dumps(item, indent=2)}\n\n"
            else:
                knowledge_content += f"Information: {str(item)}\n\n"
    
    # Base prompt for RMIT Enrolment Advisor
    base_prompt = f"""
You are an expert RMIT University Enrolment Advisor assistant. Your primary role is to help RMIT students with:

1. Course enrolment procedures and deadlines
2. Academic planning and course selection
3. Enrolment requirements and documentation
4. Fee payment and financial information
5. Academic policies and regulations
6. Contact information for relevant departments

INSTRUCTIONS:
- Provide accurate, helpful, and actionable advice
- Use official RMIT information when available
- Be specific about deadlines, requirements, and procedures
- Direct students to appropriate resources and contacts
- Maintain a helpful and professional tone
- If you're unsure about specific details, advise students to contact RMIT directly

{knowledge_content}

IMPORTANT: Base your responses on the knowledge base provided above. If information is not available in the knowledge base, clearly state this and suggest contacting RMIT directly.
"""
    
    # Apply prompt tuning
    enhanced_prompt = tune_prompt_for_context(base_prompt, user_question)
    
    return enhanced_prompt

# === Invoke Claude via Bedrock === #
def invoke_bedrock(prompt_text, max_tokens=1000, temperature=0.3, top_p=0.9):
    """Invoke Claude model via AWS Bedrock"""
    try:
        credentials = get_credentials(USERNAME, PASSWORD)
        if not credentials:
            return "Authentication failed. Please check your credentials."

        bedrock_runtime = boto3.client(
            "bedrock-runtime",
            region_name=REGION,
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretKey"],
            aws_session_token=credentials["SessionToken"],
        )

        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "messages": [{"role": "user", "content": prompt_text}]
        }

        response = bedrock_runtime.invoke_model(
            body=json.dumps(payload),
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json"
        )

        result = json.loads(response["body"].read())
        return result["content"][0]["text"]
    
    except Exception as e:
        return f"Error generating response: {str(e)}"

# === Streamlit UI === #
def main():
    st.set_page_config(
        page_title="RMIT Enrolment Advisor",
        page_icon="🎓",
        layout="wide"
    )

    # Custom CSS for better UI
    st.markdown("""
    <style>
    .main-header {
        text-align: center;
        padding: 1rem 0;
        background: linear-gradient(90deg, #e31837, #ff6b6b);
        color: white;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    .chat-container {
        background: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 4px solid #e31837;
    }
    .knowledge-status {
        background: #e8f5e8;
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid #28a745;
        margin-bottom: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)

    # Header
    st.markdown(f"""
    <div class="main-header">
        <h1>{APP_TITLE}</h1>
        <p>{APP_SUBTITLE}</p>
    </div>
    """, unsafe_allow_html=True)

    # Knowledge base status
    with st.container():
        knowledge_base = load_knowledge_base()
        if knowledge_base:
            st.markdown(f"""
            <div class="knowledge-status">
                📚 <strong>Knowledge Base Status:</strong> Loaded {len(knowledge_base)} information sources
                <br>💡 <em>Ready to assist with RMIT enrolment questions!</em>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.warning("⚠️ No knowledge base found. Place your JSON/PDF files in the 'knowledge_base' folder for better responses.")

    # Main chat interface
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    
    # Chat input
    user_question = st.text_area(
        "💬 **Ask your RMIT enrolment question:**",
        placeholder=CHAT_PLACEHOLDER,
        height=100,
        key="user_input"
    )

    # Action buttons
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        ask_button = st.button("🚀 Get Answer", type="primary", use_container_width=True)
    
    with col2:
        if st.button("🔄 Clear", use_container_width=True):
            st.rerun()
    
    with col3:
        if st.button("📋 Sample Questions", use_container_width=True):
            st.session_state.show_samples = not st.session_state.get('show_samples', False)

    # Sample questions
    if st.session_state.get('show_samples', False):
        st.markdown("### 💡 Sample Questions:")
        sample_questions = [
            "How do I enrol in courses for next semester?",
            "What are the enrolment deadlines for 2025?",
            "How do I pay my course fees?",
            "What documents do I need for enrolment?",
            "Who do I contact about enrolment issues?",
            "How do I change my course enrolment?",
        ]
        for i, question in enumerate(sample_questions, 1):
            st.markdown(f"**{i}.** {question}")

    # Process question
    if ask_button and user_question.strip():
        with st.spinner(PROCESSING_MESSAGE):
            try:
                # Build enhanced prompt
                prompt = build_prompt(user_question, knowledge_base)
                
                # Get response
                response = invoke_bedrock(prompt)
                
                # Display response
                st.success(SUCCESS_MESSAGE)
                st.markdown("### 🤖 **RMIT Enrolment Advisor Response:**")
                st.markdown(response)
                
                # Additional resources
                st.markdown("---")
                st.markdown("### 📞 **Need More Help?**")
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("""
                    **RMIT Student Services:**
                    - 📧 ask.rmit@rmit.edu.au
                    - 📞 +61 3 9925 5000
                    """)
                with col2:
                    st.markdown("""
                    **Online Resources:**
                    - [RMIT Student Portal](https://www.rmit.edu.au/students)
                    - [Enrolment Guide](https://www.rmit.edu.au/students/my-course/enrolment)
                    """)
                
            except Exception as e:
                st.error(f"{ERROR_MESSAGE}\nDetails: {str(e)}")
    
    elif ask_button:
        st.warning("Please enter a question before clicking 'Get Answer'.")

    st.markdown('</div>', unsafe_allow_html=True)

    # Footer
    st.markdown("---")
    st.markdown("*This chatbot provides general guidance. For official information, always refer to RMIT's official website or contact RMIT directly.*")

if __name__ == "__main__":
    main()