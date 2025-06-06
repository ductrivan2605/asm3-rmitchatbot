# RMIT Advisor Chatbot
# Author: Van Duc Tri - s3978223
# Features: Database Integration, Advanced Web Scraping, Chat History
# Updated: June 2025

import streamlit as st
import json
import boto3
import os
import re
import requests
from datetime import datetime, timedelta
from PyPDF2 import PdfReader
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
from bs4 import BeautifulSoup
import urllib.parse
import sqlite3
import hashlib
import uuid
from typing import List, Dict, Optional
import xml.etree.ElementTree as ET

# Load environment variables
load_dotenv()

# === Configuration Labels === #
APP_TITLE = "RMIT CONNECT HELPER"
APP_SUBTITLE = "Your intelligent assistant for RMIT services and academic support 🤓"
PROCESSING_MESSAGE = "Processing your question... 🤔"
SUCCESS_MESSAGE = "Response generated successfully 🗿"
ERROR_MESSAGE = "An error occurred. Please try again. 😭"

# === AWS Configuration === #
REGION = os.getenv("AWS_REGION", "us-east-1")
MODEL_ID = os.getenv("MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
IDENTITY_POOL_ID = os.getenv("IDENTITY_POOL_ID")
USER_POOL_ID = os.getenv("USER_POOL_ID")
APP_CLIENT_ID = os.getenv("APP_CLIENT_ID")
USERNAME = os.getenv("AWS_USERNAME")
PASSWORD = os.getenv("AWS_PASSWORD")

# === Database Configuration === #
DB_PATH = "rmit_chatbot.db"
KNOWLEDGE_BASE_DIR = "knowledge_base"

# === Database Schema and Operations === #
class DatabaseManager:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database with required tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Chat sessions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    session_name TEXT
                )
            ''')
            
            # Chat messages table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_messages (
                    message_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    message_type TEXT CHECK(message_type IN ('user', 'assistant')),
                    content TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    tokens_used INTEGER,
                    response_time REAL,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions (session_id)
                )
            ''')
            
            # Knowledge base table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS knowledge_base (
                    kb_id TEXT PRIMARY KEY,
                    source_type TEXT CHECK(source_type IN ('web', 'pdf', 'manual')),
                    source_url TEXT,
                    title TEXT,
                    content TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    content_hash TEXT,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            
            # User feedback table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_feedback (
                    feedback_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    message_id TEXT,
                    rating INTEGER CHECK(rating BETWEEN 1 AND 5),
                    feedback_text TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions (session_id),
                    FOREIGN KEY (message_id) REFERENCES chat_messages (message_id)
                )
            ''')
            
            conn.commit()
    
    def create_session(self, user_id: str = "anonymous") -> str:
        """Create a new chat session"""
        session_id = str(uuid.uuid4())
        session_name = f"Chat Session {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO chat_sessions (session_id, user_id, session_name)
                VALUES (?, ?, ?)
            ''', (session_id, user_id, session_name))
            conn.commit()
        
        return session_id
    
    def save_message(self, session_id: str, message_type: str, content: str, 
                    tokens_used: int = 0, response_time: float = 0.0) -> str:
        """Save a chat message to database"""
        message_id = str(uuid.uuid4())
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO chat_messages 
                (message_id, session_id, message_type, content, tokens_used, response_time)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (message_id, session_id, message_type, content, tokens_used, response_time))
            
            # Update last activity
            cursor.execute('''
                UPDATE chat_sessions 
                SET last_activity = CURRENT_TIMESTAMP 
                WHERE session_id = ?
            ''', (session_id,))
            
            conn.commit()
        
        return message_id
    
    def get_chat_history(self, session_id: str, limit: int = 10) -> List[Dict]:
        """Retrieve chat history for a session"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT message_type, content, timestamp 
                FROM chat_messages 
                WHERE session_id = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (session_id, limit))
            
            messages = []
            for row in cursor.fetchall():
                messages.append({
                    'role': row[0],
                    'content': row[1],
                    'timestamp': row[2]
                })
            
            return list(reversed(messages))  # Return in chronological order
    
    def save_knowledge_item(self, source_type: str, source_url: str, title: str, 
                          content: str) -> str:
        """Save knowledge base item"""
        kb_id = str(uuid.uuid4())
        content_hash = hashlib.md5(content.encode()).hexdigest()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Check if content already exists
            cursor.execute('''
                SELECT kb_id FROM knowledge_base 
                WHERE content_hash = ? AND is_active = 1
            ''', (content_hash,))
            
            if cursor.fetchone():
                return "duplicate"
            
            cursor.execute('''
                INSERT INTO knowledge_base 
                (kb_id, source_type, source_url, title, content, content_hash)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (kb_id, source_type, source_url, title, content, content_hash))
            
            conn.commit()
        
        return kb_id
    
    def get_knowledge_base(self, limit: int = 100) -> List[Dict]:
        """Retrieve active knowledge base items"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT source_type, source_url, title, content, last_updated
                FROM knowledge_base 
                WHERE is_active = 1 
                ORDER BY last_updated DESC 
                LIMIT ?
            ''', (limit,))
            
            items = []
            for row in cursor.fetchall():
                items.append({
                    'source_type': row[0],
                    'source_url': row[1],
                    'title': row[2],
                    'content': row[3],
                    'last_updated': row[4]
                })
            
            return items

# Initialize database manager
db_manager = DatabaseManager()

# === Enhanced Web Scraping with Sitemap === #
class RMITWebScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.base_url = "https://www.rmit.edu.au"
        self.sitemap_url = "https://www.rmit.edu.au/sitemap.xml"
    
    def get_sitemap_urls(self, keywords: List[str] = None) -> List[str]:
        """Extract relevant URLs from RMIT sitemap"""
        try:
            response = requests.get(self.sitemap_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            urls = []
            
            # Default keywords for RMIT student services
            if not keywords:
                keywords = [
                    'rmit', 'enrol', 'enroll', 'course', 'program', 'degree', 'study',
                    'student', 'academic', 'assignment', 'exam', 'lecture', 'tutorial',
                    'fee', 'payment', 'scholarship', 'deadline', 'date', 'timetable',
                    'library', 'campus', 'international', 'domestic', 'credit', 'result',
                    'transcript', 'plagiarism', 'extension', 'graduation', 'certificate',
                    'diploma', 'bachelor', 'master', 'phd', 'research', 'thesis',
                    'university', 'college', 'education', 'tuition', 'admission',
                    'enrollment', 'enrolment', 'assessment', 'grade', 'marks',
                    'faculty', 'school', 'department', 'tutor', 'professor',
                    'accommodation', 'housing', 'campus', 'melbourne', 'vn',
                    'au', 'online', 'distance', 'learning', 'canvas',
                    'lms', 'portal', 'student id', 'id card',
                    'orientation', 'workshop', 'seminar', 'conference'
                ]
            
            # Extract URLs containing relevant keywords
            for url_elem in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}url'):
                loc_elem = url_elem.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
                if loc_elem is not None:
                    url = loc_elem.text
                    if any(keyword in url.lower() for keyword in keywords):
                        urls.append(url)
            
            return urls[:10]  # Limit to first 10 relevant URLs
            
        except Exception as e:
            st.warning(f"Could not fetch sitemap: {str(e)}")
            return self._get_fallback_urls()
    
    def _get_fallback_urls(self) -> List[str]:
        """Fallback URLs if sitemap fails"""
        return [
            "https://www.rmit.edu.au/study-with-us",
            "https://www.rmit.edu.au/enrolment",
            "https://www.rmit.edu.au/students/my-course/important-dates",
            "https://www.rmit.edu.au/students/support-services/study-support",
            "https://research.rmit.edu.au",
            "https://www.rmit.edu.au/study-with-us/levels-of-study/undergraduate-study",
            "https://www.rmit.edu.au/study-with-us/levels-of-study/postgraduate-study"
        ]
    
    def scrape_page(self, url: str) -> Dict:
        """Scrape individual RMIT page"""
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()
            
            # Extract content
            title = soup.find('title')
            title_text = title.get_text().strip() if title else "RMIT Page"
            
            # Get main content
            main_content = (
                soup.find('main') or 
                soup.find('div', class_='content') or 
                soup.find('div', {'id': 'content'}) or
                soup.find('body')
            )
            
            content_text = ""
            if main_content:
                # Extract text from relevant elements
                for element in main_content.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'li', 'div']):
                    text = element.get_text(strip=True)
                    if text and len(text) > 20:  # Filter short text
                        content_text += f"{text}\n"
            
            # Clean content
            content_text = re.sub(r'\s+', ' ', content_text.strip())
            content_text = re.sub(r'[^\w\s\-.,!?():$%&]', '', content_text)
            
            return {
                'url': url,
                'title': title_text,
                'content': content_text,
                'scraped_at': datetime.now().isoformat(),
                'success': True
            }
            
        except Exception as e:
            return {
                'url': url,
                'title': f"Error scraping {url}",
                'content': f"Failed to scrape: {str(e)}",
                'scraped_at': datetime.now().isoformat(),
                'success': False
            }

# Initialize web scraper
scraper = RMITWebScraper()

# === Cached AWS Credentials === #
@st.cache_resource(ttl=3000)  # Cache for 50 minutes (TTL is 1 hour)
def get_cached_credentials(username: str, password: str) -> Optional[Dict]:
    """Get cached AWS credentials with automatic refresh"""
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

# === Knowledge Base Management === #
@st.cache_data(ttl=1800)  # Cache for 30 minutes
def load_enhanced_knowledge_base() -> List[Dict]:
    """Load knowledge base with database integration and web scraping"""
    
    # First, try to load from database
    db_knowledge = db_manager.get_knowledge_base()
    
    # If database is empty or outdated, refresh from web
    if not db_knowledge or should_refresh_knowledge():
        st.info("🔄 Refreshing knowledge base from RMIT website...")
        refresh_knowledge_base()
        db_knowledge = db_manager.get_knowledge_base()
    
    return db_knowledge

def should_refresh_knowledge() -> bool:
    """Check if knowledge base needs refreshing (every 6 hours)"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT MAX(last_updated) FROM knowledge_base WHERE is_active = 1
            ''')
            result = cursor.fetchone()
            
            if not result[0]:
                return True
            
            last_updated = datetime.fromisoformat(result[0])
            return (datetime.now() - last_updated) > timedelta(hours=6)
    except:
        return True

def refresh_knowledge_base():
    """Refresh knowledge base from RMIT website"""
    try:
        # Get relevant URLs from sitemap
        urls = scraper.get_sitemap_urls()
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, url in enumerate(urls):
            status_text.text(f"Scraping: {url}")
            
            # Scrape page
            page_data = scraper.scrape_page(url)
            
            if page_data['success'] and len(page_data['content']) > 100:
                # Save to database
                db_manager.save_knowledge_item(
                    source_type='web',
                    source_url=page_data['url'],
                    title=page_data['title'],
                    content=page_data['content']
                )
            
            progress_bar.progress((i + 1) / len(urls))
        
        status_text.text("✅ Knowledge base updated successfully!")
        
    except Exception as e:
        st.error(f"Error refreshing knowledge base: {str(e)}")

# === Question Relevance Check === #
def is_rmit_related(question: str) -> bool:
    """Check if the question is related to RMIT or academic topics"""
    rmit_keywords = [
        'rmit', 'enrol', 'enroll', 'course', 'program', 'degree', 'study', 
        'student', 'academic', 'assignment', 'exam', 'lecture', 'tutorial',
        'fee', 'payment', 'scholarship', 'deadline', 'date', 'timetable',
        'library', 'campus', 'international', 'domestic', 'credit', 'result',
        'transcript', 'plagiarism', 'extension', 'graduation', 'certificate',
        'diploma', 'bachelor', 'master', 'phd', 'research', 'thesis',
        'university', 'college', 'education', 'tuition', 'admission',
        'enrollment', 'enrolment', 'assessment', 'grade', 'marks',
        'faculty', 'school', 'department', 'tutor', 'professor',
        'accommodation', 'housing', 'campus', 'melbourne', 'vietnam',
        'spain', 'online', 'distance', 'learning', 'canvas',
        'blackboard', 'lms', 'portal', 'student id', 'id card',
        'orientation', 'workshop', 'seminar', 'conference'
    ]
    
    question_lower = question.lower()
    return any(keyword in question_lower for keyword in rmit_keywords)

# === Prompt Building === #
def build_enhanced_prompt(user_question: str, chat_history: List[Dict] = None) -> str:
    """Build enhanced prompt with context and knowledge base"""
    
    # First check if the question is relevant
    if not is_rmit_related(user_question):
        return "OFF_TOPIC"
    
    knowledge_base = load_enhanced_knowledge_base()
    
    # Build context from chat history
    context_section = ""
    if chat_history and len(chat_history) > 1:
        context_section = "\n\n### CONVERSATION CONTEXT:\n"
        for msg in chat_history[-4:]:  # Last 4 messages for context
            role = "User" if msg['role'] == 'user' else "Assistant"
            context_section += f"{role}: {msg['content'][:200]}...\n"
    
    # Build knowledge base section
    knowledge_section = ""
    if knowledge_base:
        knowledge_section = "\n\n### RMIT KNOWLEDGE BASE (Latest from Official Website):\n"
        for item in knowledge_base[:10]:  # Top 10 most recent items
            knowledge_section += f"\n--- {item['title']} ---\n"
            knowledge_section += f"Source: {item['source_url']}\n"
            knowledge_section += f"Content: {item['content'][:500]}...\n\n"
    
    # Enhanced system prompt
    system_prompt = f"""
You are RMIT Connect Helper, an expert AI assistant for RMIT University students. You have access to the latest information from RMIT's official website and maintain conversation context.

## YOUR CAPABILITIES:
- Provide accurate, up-to-date information about RMIT enrolment,SPECIFIC courses, and services
- Remember previous questions in our conversation
- Give step-by-step guidance for complex procedures
- Direct students to appropriate resources and contacts

## RESPONSE GUIDELINES:
- Use information from the knowledge base when available
- Be specific about deadlines, requirements, and procedures
- Provide actionable steps and clear instructions
- Reference official RMIT sources when possible
- If unsure, recommend contacting RMIT directly
- Maintain conversation context and refer to previous questions when relevant
- ONLY answer questions related to RMIT University and academic topics
- Politely decline to answer any non-RMIT related questions except for continuing the conversation
## KNOWLEDGE BASE:
- This knowledge base contains the latest information from RMIT's official website, including enrolment procedures, course details, student services, and academic support.
## CONTEXT AND KNOWLEDGE:
- Use the following context and knowledge base to answer the user's question:
{context_section}

{knowledge_section}

## CURRENT QUESTION: {user_question}

Please provide a comprehensive, helpful response based on the latest RMIT information available.
If the question is not related to RMIT, politely decline to answer.
"""
    
    return system_prompt

# === Bedrock Invocation === #
def invoke_bedrock_enhanced(prompt_text: str, max_tokens: int = 500, 
                          temperature: float = 0.3) -> tuple:
    """Enhanced Bedrock invocation with timing and token tracking"""
    start_time = datetime.now()
    
    try:
        credentials = get_cached_credentials(USERNAME, PASSWORD)
        if not credentials:
            return "Authentication failed. Please check your credentials.", 0, 0.0

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
            "top_p": 0.9,
            "messages": [{"role": "user", "content": prompt_text}]
        }

        response = bedrock_runtime.invoke_model(
            body=json.dumps(payload),
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json"
        )

        result = json.loads(response["body"].read())
        response_text = result["content"][0]["text"]
        
        # Calculate metrics
        response_time = (datetime.now() - start_time).total_seconds()
        estimated_tokens = len(prompt_text.split()) + len(response_text.split())
        
        return response_text, estimated_tokens, response_time
    
    except Exception as e:
        response_time = (datetime.now() - start_time).total_seconds()
        return f"Error generating response: {str(e)}", 0, response_time

# === Main Streamlit Application === #
def main():
    st.set_page_config(
        page_title="RM-AI-T",
        page_icon="🤓",
        layout="wide"
    )

    # Custom CSS
    st.markdown("""
    <style>
    .main-header {
        text-align: center;
        padding: 1.5rem 0;
        background: linear-gradient(135deg, #E60028, #E66947, #F4A261);
        color: white;
        border-radius: 15px;
        margin-bottom: 2rem;
        box-shadow: 0 4px 15px rgba(230, 0, 40, 0.3);
    }
    
    .stats-container {
        display: flex;
        justify-content: space-around;
        background: #00AAFF;
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    
    .stat-item {
        text-align: center;
    }
    
    .chat-message {
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 10px;
        border-left: 4px solid #E60028;
        background: #00AAFF;
    }
    
    .response-metrics {
        font-size: 0.8em;
        color: #666;
        margin-top: 0.5rem;
    }
    
    .off-topic-warning {
        color: #ffffff;
        font-weight: bold;
        padding: 0.5rem;
        border-left: 4px solid #E60028;
        background: #00AAFF;
    }
    </style>
    """, unsafe_allow_html=True)

    # Header
    st.markdown(f"""
    <div class="main-header">
        <h1>🎓 {APP_TITLE}</h1>
        <p>{APP_SUBTITLE}</p>
    </div>
    """, unsafe_allow_html=True)

    # Initialize session state
    if 'chat_session_id' not in st.session_state:
        st.session_state.chat_session_id = db_manager.create_session()
    
    if 'messages' not in st.session_state:
        st.session_state.messages = []

    # Sidebar with statistics and controls
    with st.sidebar:
        st.markdown("## 📊 System Status")
        
        # Get statistics
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Count knowledge base items
            cursor.execute("SELECT COUNT(*) FROM knowledge_base WHERE is_active = 1")
            kb_count = cursor.fetchone()[0]
            
            # Count total messages
            cursor.execute("SELECT COUNT(*) FROM chat_messages")
            total_messages = cursor.fetchone()[0]
            
            # Count sessions today
            cursor.execute("""
                SELECT COUNT(*) FROM chat_sessions 
                WHERE DATE(created_at) = DATE('now')
            """)
            sessions_today = cursor.fetchone()[0]
        
        # Display stats
        st.markdown(f"""
        <div class="stats-container">
            <div class="stat-item">
                <strong>{kb_count}</strong><br>
                Knowledge Items
            </div>
            <div class="stat-item">
                <strong>{total_messages}</strong><br>
                Total Messages
            </div>
            <div class="stat-item">
                <strong>{sessions_today}</strong><br>
                Sessions Today
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Control buttons
        if st.button("🔄 Refresh Knowledge Base", use_container_width=True):
            st.cache_data.clear()
            refresh_knowledge_base()
            st.success("Knowledge base refreshed!")
        
        if st.button("🗑️ Clear Chat History", use_container_width=True):
            st.session_state.messages = []
            st.session_state.chat_session_id = db_manager.create_session()
            st.rerun()
        
        if st.button("📊 Export Chat History", use_container_width=True):
            chat_history = db_manager.get_chat_history(st.session_state.chat_session_id, 100)
            if chat_history:
                df = pd.DataFrame(chat_history)
                csv = df.to_csv(index=False)
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name=f"rmit_chat_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )

    # Main chat interface
    st.markdown("## 💬 Chat with RMIT Connect Helper")
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message.get("off_topic", False):
                st.markdown(f'<div class="off-topic-warning">{message["content"]}</div>', unsafe_allow_html=True)
            else:
                st.markdown(message["content"])
            
            if "metrics" in message and message["metrics"]["tokens"] > 0:
                st.markdown(f"""
                <div class="response-metrics">
                    🏃‍♂️‍➡️ Response time: {message['metrics']['response_time']:.2f}s | 
                    🤔 Estimated tokens: {message['metrics']['tokens']}
                </div>
                """, unsafe_allow_html=True)

    # Chat input
    if prompt := st.chat_input("Ask me anything about RMIT..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Save user message to database
        db_manager.save_message(
            st.session_state.chat_session_id, 
            "user", 
            prompt
        )
        
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generate assistant response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                # Get chat history for context
                chat_history = db_manager.get_chat_history(st.session_state.chat_session_id)
                
                # Build enhanced prompt
                enhanced_prompt = build_enhanced_prompt(prompt, chat_history)
                
                # Check if question is off-topic
                if enhanced_prompt == "OFF_TOPIC":
                    response = (
                        "I'm sorry, but I can only answer questions related to RMIT University "
                        "and academic topics. Please ask me about RMIT courses, enrollment, "
                        "student services, or other university-related matters."
                    )
                    tokens = 0
                    response_time = 0
                    off_topic = True
                else:
                    # Get response
                    response, tokens, response_time = invoke_bedrock_enhanced(enhanced_prompt)
                    off_topic = False
                
                # Display response
                if off_topic:
                    st.markdown(f'<div class="off-topic-warning">{response}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(response)
                
                # Save assistant message to database
                db_manager.save_message(
                    st.session_state.chat_session_id,
                    "assistant",
                    response,
                    tokens,
                    response_time
                )
                
                # Add to session state
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": response,
                    "metrics": {
                        "response_time": response_time,
                        "tokens": tokens
                    },
                    "off_topic": off_topic
                })

    # Show additional resources only when there are messages
    if st.session_state.messages:
        st.markdown("---")
        
        # Create expandable section for additional resources
        with st.expander("📞 **Need More Help?** - Click to expand"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("""
                **RMIT Student Services:**
                - 📧 ask.rmit@rmit.edu.au
                - 📞 +61 3 9925 5000
                - 🌐 [Student Portal](https://www.rmit.edu.au/students)
                """)
            with col2:
                st.markdown("""
                **Quick Links:**
                - [Enrolment Guide](https://www.rmit.edu.au/students/my-course/enrolment)
                - [Important Dates](https://www.rmit.edu.au/students/student-essentials/important-dates)
                - [Fees & Payments](https://www.rmit.edu.au/students/student-essentials/fees-and-payments)
                """)

    # Footer
    st.markdown("---")
    st.markdown("""
    *This enhanced chatbot provides guidance based on RMIT's official website. 
    Chat history is saved locally for context. For official information, always refer to RMIT's website.*
    """)

if __name__ == "__main__":
    main()