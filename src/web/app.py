"""
Deutsche Telekom Tariff Simulator Backend
-------------------------------
Flask app using CrewAI to simulate a conversation between a Deutsche Telekom customer (random persona) and a Deutsche Telekom bot, with real tariff data from tariffs.md.
"""

import os
import json
import time
import uuid
import random
import requests
import threading
from datetime import datetime
from typing import Any, List, Optional, Dict, Generator
from flask import Flask, render_template, jsonify, Response, request, stream_with_context, session
from src.agents.crew_manager import TelekomCrewManager
from src.core.llm_adapter import get_llm, get_llm_logs, clear_llm_logs
from src.data.prompts import (
    TELEKOM_TASK_PROMPT,
    CUSTOMER_TASK_PROMPT,
    TERMINATOR_TASK_PROMPT,
    TERMINATOR_USER_TASK_PROMPT,
    TERMINATOR_LAST_EXCHANGE_PROMPT,
    CONFIRMATION_TASK_PROMPT,
    CUSTOMER_INTRO_PROMPT
)
from src.data.personas import PERSONAS
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# === Constants ===
TARIFFS_FILE = os.getenv('TARIFFS_FILE', 'src/data/tariffs.md')
CONVERSATION_HISTORY_DIR = os.getenv('CONVERSATION_HISTORY_DIR', 'conversation_history')
SESSION_MAX_AGE_MINUTES = int(os.getenv('SESSION_MAX_AGE_MINUTES', '30'))
MAX_TURNS = 10

# === Flask App ===
app = Flask(__name__, 
           static_folder='static',
           template_folder='templates')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Disable caching
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Ensure conversation history directory exists
os.makedirs(CONVERSATION_HISTORY_DIR, exist_ok=True)

# Note: We're now using crew_manager.execute_single_task instead of this function
# This comment is kept for reference of the original implementation

# === Session Management ===
class SessionManager:
    def __init__(self):
        self.sessions = {}

    def get_session(self, session_id: str) -> Dict:
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                'conversation_history': [],
                'persona': None,
                'last_activity': datetime.now()
            }
        self.update_activity(session_id)
        return self.sessions[session_id]

    def update_activity(self, session_id: str):
        if session_id in self.sessions:
            self.sessions[session_id]['last_activity'] = datetime.now()

    def cleanup_old_sessions(self):
        now = datetime.now()
        expired_sessions = [
            sid for sid, session in self.sessions.items()
            if (now - session['last_activity']).total_seconds() > SESSION_MAX_AGE_MINUTES * 60
        ]
        for sid in expired_sessions:
            del self.sessions[sid]

session_manager = SessionManager()

# Initialize the CrewAI manager
crew_manager = TelekomCrewManager()

# === Helper Functions ===
def read_tariffs(file_path: str = TARIFFS_FILE) -> str:
    """Read the tariffs Markdown file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except Exception as e:
        print(f"Error reading tariffs file: {str(e)}")
        return "Error: Tariff information not available."

def format_conversation(history: List[Dict[str, str]]) -> str:
    """Format conversation history for task descriptions."""
    formatted = ""
    for msg in history:
        role = msg['role'].capitalize()
        formatted += f"{role}: {msg['content']}\n\n"
    return formatted.strip()

def sse_message(data: dict) -> str:
    """Format a message for Server-Sent Events (SSE)."""
    return f"data: {json.dumps(data)}\n\n"


def send_llm_logs() -> List[str]:
    """Get LLM logs and clear them."""
    logs = get_llm_logs()
    clear_llm_logs()
    return logs

def save_conversation(session_id: str, conversation_data: Dict):
    """Save conversation data to a JSON file in the conversation_history directory."""
    try:
        filename = f"{session_id}_{int(time.time())}.json"
        filepath = os.path.join(CONVERSATION_HISTORY_DIR, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(conversation_data, f, indent=2)
    except Exception as e:
        print(f"Error saving conversation: {str(e)}")

def get_last_exchange(history: List[Dict[str, str]]) -> str:
    """Get the last exchange (last customer message and bot response) from conversation history."""
    if len(history) < 2:
        return "No conversation history yet."
    
    # Find the last customer and bot messages
    last_customer_msg = next((msg for msg in reversed(history) if msg['role'] == 'customer'), None)
    last_bot_msg = next((msg for msg in reversed(history) if msg['role'] == 'bot'), None)
    
    if last_customer_msg and last_bot_msg:
        return f"Customer: {last_customer_msg['content']}\n\nBot: {last_bot_msg['content']}"
    return "Incomplete conversation exchange."

# === Routes ===
@app.route('/')
def home():
    """Serve the main simulator page."""
    return render_template('index.html')

@app.route('/simulate')
def simulate_conversation() -> Response:
    """Simulate a conversation between a Deutsche Telekom customer and the bot, streaming results via SSE."""
    def generate():
        try:
            session_id = request.args.get('session_id', '')
            if not session_id:
                yield sse_message({'error': 'No session ID provided'})
                return

            simulator_mode = request.args.get('simulator_mode', '1') == '1'
            session = session_manager.get_session(session_id)
            session_manager.update_activity(session_id)

            if not simulator_mode:
                return

            tarifs_md = read_tariffs()
            persona = random.choice(PERSONAS)
            persona_name = persona["name"]
            persona_needs = persona["needs"]
            session['persona'] = persona_name

            yield sse_message({'persona_name': persona_name})

            bot_greeting = "Hello, I am a Deutsche Telekom agent. How can I help you with your tariff today?"
            session['conversation_history'].append({"role": "bot", "content": bot_greeting})
            yield sse_message({'role': 'bot', 'content': bot_greeting})
            
            # First customer message
            status_msg = f"{persona_name} (Customer) is about to speak (first message)."
            print(f"[SIM] {status_msg}")
            yield sse_message({'status': status_msg})
            
            # Create the first customer task using the crew manager
            customer_task = crew_manager.get_customer_intro(
                persona_name=persona_name,
                persona_needs=persona_needs
            )
            
            # Execute the customer task
            customer_message = crew_manager.execute_single_task(customer_task, max_retries=1, timeout=120)
            session['conversation_history'].append({"role": "customer", "content": customer_message})
            yield sse_message({'role': 'customer', 'content': customer_message})
            
            # Send any LLM logs
            llm_logs = send_llm_logs()
            for log in llm_logs:
                yield sse_message({'log': log, 'log_type': 'llm'})

            # Main conversation loop
            for turn in range(MAX_TURNS):
                # Bot response
                status_msg = "Telekom Agent: Preparing response..."
                print(f"[SIM] {status_msg}")
                yield sse_message({'status': status_msg})

                # Calculate conversation turn number
                turn_number = len([msg for msg in session['conversation_history'] if msg['role'] == 'customer'])
                
                # Create bot task using crew manager
                bot_task = crew_manager.get_telekom_response_task(
                    conversation_history=format_conversation(session['conversation_history']),
                    tariffs=tarifs_md,
                    persona=f"{persona_name}. {persona_needs}"
                )
                
                # Get the previous customer messages to check for repetition
                prev_customer_msgs = [msg['content'] for msg in session['conversation_history'] if msg['role'] == 'customer']
                
                # Execute the bot task with monitoring but no timeout fallback
                status_msg = "Telekom Agent: Analyzing customer needs and generating response..."
                print(f"[SIM] {status_msg}")
                yield sse_message({'status': status_msg})
                
                bot_message = crew_manager.execute_single_task(bot_task, max_retries=1, timeout=120)
                session['conversation_history'].append({"role": "bot", "content": bot_message})
                yield sse_message({'role': 'bot', 'content': bot_message})
                
                # Send any LLM logs
                llm_logs = send_llm_logs()
                for log in llm_logs:
                    yield sse_message({'log': log, 'log_type': 'llm'})
                
                # Create the customer task using crew manager
                customer_task = crew_manager.get_customer_response_task(
                    persona_name=persona_name,
                    persona_needs=persona_needs,
                    conversation_history=format_conversation(session['conversation_history']),
                    bot_message=bot_message,
                    prev_customer_msgs=prev_customer_msgs
                )
                
                # Execute customer task with monitoring
                status_msg = "Customer is responding (this may take a minute)..."
                print(f"[SIM] {status_msg}")
                yield sse_message({'status': status_msg})
                
                # Execute the customer task with monitoring but no timeout fallback
                customer_message = crew_manager.execute_single_task(customer_task, max_retries=1, timeout=120)
                
                # Add customer message to conversation history
                session['conversation_history'].append({"role": "customer", "content": customer_message})
                yield sse_message({'role': 'customer', 'content': customer_message})
                
                # Check if customer has chosen a plan
                status_msg = "Terminator Agent: Analyzing customer message for plan selection..."
                print(f"[SIM] {status_msg}")
                yield sse_message({'status': status_msg})
                
                # Log the message being analyzed
                log_msg = f"[SIM] Analyzing message: '{customer_message[:50]}{'...' if len(customer_message) > 50 else ''}'" 
                print(log_msg)
                yield sse_message({'log': log_msg})
                
                # Quick check for question marks as an early indicator
                if '?' in customer_message:
                    log_msg = f"[SIM] Quick check: Message contains question mark, will likely not be a plan selection"
                    print(log_msg)
                    yield sse_message({'log': log_msg, 'log_type': 'warning'})
                
                # Create the terminator task using crew manager
                terminator_task = crew_manager.get_terminator_task(
                    user_message=customer_message
                )
                
                # Use our monitoring mechanism for the terminator task without timeout fallback
                terminator_response = crew_manager.execute_single_task(terminator_task, max_retries=1, timeout=60)
                
                # Check if the customer has chosen a plan and log the decision
                log_msg = f"[SIM] Terminator decision: {terminator_response}"
                print(log_msg)
                yield sse_message({'log': log_msg})
                
                if terminator_response.upper().startswith("YES"):
                    # Extract the plan name from the response
                    plan_name = terminator_response.replace("YES:", "").strip()
                    
                    log_msg = f"[SIM] Customer has selected a plan: {plan_name}"
                    print(log_msg)
                    yield sse_message({'log': log_msg, 'log_type': 'success'})
                    
                    # Create the confirmation task
                    confirmation_task = crew_manager.get_confirmation_task(plan_name)
                    
                    # Execute the confirmation task
                    status_msg = "Generating welcome message..."
                    print(f"[SIM] {status_msg}")
                    yield sse_message({'status': status_msg})
                    
                    confirmation_message = crew_manager.execute_single_task(confirmation_task, max_retries=1, timeout=60)
                    session['conversation_history'].append({"role": "bot", "content": confirmation_message})
                    yield sse_message({'role': 'bot', 'content': confirmation_message})
                    
                    # Send any LLM logs
                    llm_logs = send_llm_logs()
                    for log in llm_logs:
                        yield sse_message({'log': log, 'log_type': 'llm'})
                    
                    # Save the conversation
                    save_conversation(session_id, {
                        'persona': f"{persona_name}: {persona_needs}",
                        'conversation': session['conversation_history'],
                        'selected_plan': plan_name
                    })
                    
                    # End the conversation
                    log_msg = f"[SIM] Conversation complete. Customer selected: {plan_name}"
                    print(log_msg)
                    yield sse_message({'log': log_msg, 'log_type': 'success'})
                    yield sse_message({'status': 'Conversation ended - plan selected'})
                    yield sse_message({'end': True})
                    return
            
            # If we reach here, the conversation has reached the maximum number of turns
            yield sse_message({'status': 'Conversation ended - maximum turns reached'})
            
        except Exception as e:
            print(f"Error in simulate_conversation: {str(e)}")
            yield sse_message({'error': f"An error occurred: {str(e)}"})
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/user_message', methods=['POST'])
def user_message() -> Response:
    """Handle user input mode: receive user message, respond with bot agent only."""
    def generate():
        try:
            data = request.get_json()
            if not data:
                yield sse_message({'error': 'No data provided'})
                return
                
            session_id = data.get('session_id', '')
            user_msg = data.get('message', '').strip()
            
            if not session_id or not user_msg:
                yield sse_message({'error': 'Missing session ID or message'})
                return
                
            session = session_manager.get_session(session_id)
            session_manager.update_activity(session_id)
            
            # Add user message to conversation history
            session['conversation_history'].append({"role": "customer", "content": user_msg})
            
            # Read tariffs
            tarifs_md = read_tariffs()
            
            # Check if user has selected a plan
            status_msg = "Terminator Agent: Analyzing your message for plan selection..."
            print(f"[USER] {status_msg}")
            yield sse_message({'status': status_msg})
            
            # Log the message being analyzed
            log_msg = f"[USER] Analyzing message: '{user_msg[:50]}{'...' if len(user_msg) > 50 else ''}'" 
            print(log_msg)
            yield sse_message({'log': log_msg})
            
            # Quick check for question marks as an early indicator
            if '?' in user_msg:
                log_msg = f"[USER] Quick check: Message contains question mark, will likely not be a plan selection"
                print(log_msg)
                yield sse_message({'log': log_msg, 'log_type': 'warning'})
            
            # Create the terminator task using crew manager
            terminator_task = crew_manager.get_terminator_task(
                user_message=user_msg
            )
            
            # Execute the terminator task
            terminator_response = crew_manager.execute_single_task(terminator_task, max_retries=1, timeout=60)
            
            # Send any LLM logs
            llm_logs = send_llm_logs()
            for log in llm_logs:
                yield sse_message({'log': log, 'log_type': 'llm'})
            
            # Check if the user has chosen a plan and log the decision
            log_msg = f"[USER] Terminator decision: {terminator_response}"
            print(log_msg)
            yield sse_message({'log': log_msg})
            
            if terminator_response.upper().startswith("YES:"):
                plan_name = terminator_response[4:].strip()
                if not plan_name:
                    plan_name = "a tariff plan"
                
                log_msg = f"[USER] Customer has selected a plan: {plan_name}"
                print(log_msg)
                yield sse_message({'log': log_msg, 'log_type': 'success'})
                
                status_msg = f"Telekom Agent: Preparing confirmation for selected plan: {plan_name}"
                print(f"[USER] {status_msg}")
                yield sse_message({'status': status_msg})
                
                # Create a final confirmation task using crew manager
                confirmation_task = crew_manager.get_confirmation_task(
                    plan_name=plan_name
                )
                
                # Execute the confirmation task
                confirmation_message = crew_manager.execute_single_task(confirmation_task, max_retries=1, timeout=60)
                
                # Send any LLM logs
                llm_logs = send_llm_logs()
                for log in llm_logs:
                    yield sse_message({'log': log, 'log_type': 'llm'})
                
                # Add confirmation to conversation history
                session['conversation_history'].append({"role": "bot", "content": confirmation_message})
                yield sse_message({'role': 'bot', 'content': confirmation_message})
                
                # Save the conversation
                save_conversation(session_id, {
                    'conversation': session['conversation_history'],
                    'selected_plan': plan_name
                })
                
                # End the conversation
                log_msg = f"[USER] Conversation complete. Customer selected: {plan_name}"
                print(log_msg)
                yield sse_message({'log': log_msg, 'log_type': 'success'})
                yield sse_message({'status': 'Conversation ended - plan selected'})
                yield sse_message({'end': True})
                return
            
            # No plan selected, log the reason
            reason = terminator_response.replace("NO", "").strip()
            log_msg = f"[USER] No plan selection detected. Reason: {reason if reason else 'No explicit purchase intent'}"
            print(log_msg)
            yield sse_message({'log': log_msg, 'log_type': 'info'})
            
            # Bot response
            status_msg = "Telekom Agent: Analyzing your message and generating a response..."
            print(f"[USER] {status_msg}")
            yield sse_message({'status': status_msg})
            
            # Create bot task using crew manager
            bot_task = crew_manager.get_telekom_response_task(
                conversation_history=format_conversation(session['conversation_history']),
                tariffs=tarifs_md,
                persona="User"
            )
            
            # Execute the bot task
            bot_message = crew_manager.execute_single_task(bot_task, max_retries=1, timeout=120)
            
            # Send any LLM logs
            llm_logs = send_llm_logs()
            for log in llm_logs:
                yield sse_message({'log': log, 'log_type': 'llm'})
            
            # Add bot response to conversation history
            session['conversation_history'].append({"role": "bot", "content": bot_message})
            yield sse_message({'role': 'bot', 'content': bot_message})
            
        except Exception as e:
            print(f"Error in user_message: {str(e)}")
            yield sse_message({'error': f"An error occurred: {str(e)}"})
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')
