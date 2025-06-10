# Contributor
***VAN DUC TRI - S3978223***
## Application's related link
1. Deployed app
```
https://rm-ai-t.streamlit.app/
```
2. Presentation
```
https://docs.google.com/presentation/d/1JebUXeE7dUrxQ-_enEbHko8m7t9cF7C9kzrfxvhkNXs/edit?usp=sharing
```
# Features
- AI-Powered Chatbot using AWS Bedrock's Claude AI model that used RMIT's official website as knowledge base
- Response time and token used display.
- Chat history export and deletation.
- Data cleaning and knowledge base refresh to save memory and tokens(avoiding hallucinations).
- Duplicate content prevention.
# Technologies
- **FE and Deployment** - Streamlit
- **AI Model** - Claude 3 Haiku
- **Database** - SQLite
- **Web Scrapping** - BeautifulSoup, Requests
- **Data Processing** - Pandas, PyPDF2
# Using the app on your local machine
## Prerequisites
- Python 3.11 or higher(It is recommended to use the latest version from `https://www.python.org/downloads/` instead of downloading from Microsoft store as it's may cause a little trouble with the metadata)
- Registered account for AWS Bedrock *here*
```
https://us-east-1kopki1lpu.auth.us-east-1.amazoncognito.com/login?client_id=3h7m15971bnfah362dldub1u2p&response_type=code&scope=aws.cognito.signin.user.admin+email+openid&redirect_uri=https%3A%2F%2Fd84l1y8p4kdic.cloudfront.net
```
- Pull this repository to your local machine or download the provided zip file via submission.
## Installation
- Clone the repository/Download the zip file
```
git clone https://github.com/ductrivan2605/asm3-rmitchatbot
cd .\asm3-rmitchatbot
```
- Create virtual environment
```
python -m venv .venv
.\.venv\Scripts\activate
```
- Install dependencies
```
pip install -r requirements.txt
```
- Environment configuration
```
# Navigate to the .env file
# Add username and password inside the .env file shown as below

AWS_USERNAME="your_aws_username"
AWS_PASSWORD="your_aws_password"
```
=> After finish the installation, the file structure should include files as below:
```
asm3-rmitchatbot/
├── app.py
├── requirements.txt
├── .env
├── README.md
├── rmit_chatbot.db (created automatically)
├── knowledge_base/ (optional, for manual content)
└──.devcontainer (created automatically)
```
## Starting the application
```
streamlit run app.py
```
# Database Schema
## Chat Sessions
```
CREATE TABLE chat_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT,
    created_at TIMESTAMP,
    last_activity TIMESTAMP,
    session_name TEXT
);
```
## Chat Messages
```
CREATE TABLE chat_messages (
    message_id TEXT PRIMARY KEY,
    session_id TEXT,
    message_type TEXT,
    content TEXT,
    timestamp TIMESTAMP,
    tokens_used INTEGER,
    response_time REAL
);
```
### Knowledge Base
```
CREATE TABLE knowledge_base (
    kb_id TEXT PRIMARY KEY,
    source_type TEXT,
    source_url TEXT,
    title TEXT,
    content TEXT,
    last_updated TIMESTAMP,
    content_hash TEXT,
    is_active BOOLEAN
);
```
# Key Components
- ***DatabaseManager***: Handles SQLite operations, data integrity maintainance, ...
- ***RMITWebScraper***: Scraping content from RMIT's official website
- ***EnhancedPrompBuilding***: Knowledge base integration 
# Application's visualization
- Main Interface of the Application
![image](https://github.com/user-attachments/assets/67e56407-3b15-44bf-8944-6ef1b98e8e0a)
- Few example of user interact when prompting:
![image](https://github.com/user-attachments/assets/e96d5da9-9ca7-450c-b942-29adb6930254)
![image](https://github.com/user-attachments/assets/0cc950f0-741b-422a-b28a-54697c754b1f)
- Scraping content from RMIT's official website
![image](https://github.com/user-attachments/assets/c50a5e87-9b54-4e79-96a2-2b60a8d9426f)
- Off-topic Handling
![image](https://github.com/user-attachments/assets/98e6ebf8-852f-41e6-abd8-27b11f58c0ee)



