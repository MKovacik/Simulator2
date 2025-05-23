"""
Telecom Tariff Simulator Backend
-------------------------------
Flask app using CrewAI to simulate a conversation between a telecom customer (random persona) and a Deutsche Telekom bot, with real tariff data from Tarifs.md.
"""

import os
import random
import json
from datetime import datetime
from typing import Any, List, Optional, Dict
from flask import Flask, render_template, jsonify, Response, request, stream_with_context
from crewai import Agent, Task
import requests
from langchain.llms.base import LLM
from personas import PERSONAS

# === Constants ===
TARIFFS_FILE = 'Tarifs.md'
CONVERSATION_HISTORY_DIR = 'conversation_history'

# === Flask App ===
app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Disable caching
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Ensure conversation history directory exists
os.makedirs(CONVERSATION_HISTORY_DIR, exist_ok=True)

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
        return self.sessions[session_id]

    def update_activity(self, session_id: str):
        if session_id in self.sessions:
            self.sessions[session_id]['last_activity'] = datetime.now()

    def cleanup_old_sessions(self, max_age_minutes: int = 30):
        now = datetime.now()
        expired_sessions = [
            sid for sid, session in self.sessions.items()
            if (now - session['last_activity']).total_seconds() > max_age_minutes * 60
        ]
        for sid in expired_sessions:
            del self.sessions[sid]

session_manager = SessionManager()

# === LLM Wrapper ===
class LMStudioLLM(LLM):
    """LLM wrapper for LMStudio API."""
    base_url: str = "http://localhost:1234/v1"

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": "phi-4",
                    "messages": [
                        {"role": "system", "content": "You are a helpful AI assistant. Provide clear and concise responses."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": -1,
                    "stream": False
                }
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as e:
            print(f"Error calling LMStudio API: {str(e)}")
            raise Exception(f"Failed to get response from LMStudio: {str(e)}")

    @property
    def _llm_type(self) -> str:
        return "lmstudio"

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {"base_url": self.base_url}

# === Helper Functions ===
def read_tariffs(file_path: str = TARIFFS_FILE) -> str:
    """Read the tariffs Markdown file."""
    if not os.path.exists(file_path):
        return "Tariff data not available."
    with open(file_path, 'r') as f:
        return f.read()

def format_conversation(history: List[Dict[str, str]]) -> str:
    """Format conversation history for task descriptions."""
    formatted = []
    for msg in history:
        role = "Customer" if msg["role"] == "customer" else "Assistant"
        formatted.append(f"{role}: {msg['content']}")
    return "\n".join(formatted)

def sse_message(data: dict) -> str:
    """Format a message for Server-Sent Events (SSE)."""
    return f"data: {json.dumps(data)}\n\n"

def save_conversation(session_id: str, conversation_data: Dict):
    """Save conversation data to a JSON file in the conversation_history directory."""
    filename = os.path.join(CONVERSATION_HISTORY_DIR, f'conversation_{session_id}.json')
    with open(filename, 'w') as f:
        json.dump(conversation_data, f, indent=2)

# === Agents ===
llm = LMStudioLLM()

customer_agent = Agent(
    role='Telecom Customer',
    goal='Express needs and requirements for a new mobile tariff plan',
    backstory="""You are a real customer looking for a new mobile tariff plan. \
You have specific needs regarding data usage, international calls, and budget constraints.\
You should ask questions and express concerns naturally. Do NOT provide advice, recommendations, or information as if you were an advisor or bot. Only talk about your own needs, preferences, and questions as a customer would.""",
    llm=llm,
    verbose=True
)

bot_agent = Agent(
    role='Telecom Tariff Recommendation Bot',
    goal='Help customers find the most suitable tariff plan based on their needs',
    backstory="""You are an AI assistant specialized in recommending mobile tariff plans for Deutsche Telekom. You have access to a list of available plans and options from the file 'Tarifs.md'. Always offer and recommend only the plans and options listed in that file. You have extensive knowledge of their features and pricing. You should ask relevant questions to understand customer needs and provide personalized recommendations based on the available plans and options from 'Tarifs.md'.""",
    llm=llm,
    verbose=True
)

observer_agent = Agent(
    role='Conversation Observer',
    goal='Detect if the customer has clearly chosen a tariff plan and, if so, which one.',
    backstory="""You are an impartial observer of a conversation between a telecom customer and a Deutsche Telekom agent. Your job is to determine if the customer has clearly chosen a specific tariff plan. If so, extract the plan name. If not, state that the customer has not made a clear choice yet.""",
    llm=llm,
    verbose=False
)

# === Routes ===
@app.route('/')
def home():
    """Serve the main simulator page."""
    return render_template('index.html')

@app.route('/simulate')
def simulate_conversation() -> Response:
    """Simulate a conversation between a telecom customer and the bot, streaming results via SSE."""
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
                # User input mode: handled by /user_message
                return

            tarifs_md = read_tariffs()
            persona = random.choice(PERSONAS)
            persona_name = persona["name"]
            persona_needs = persona["needs"]
            session['persona'] = persona_name

            # Send persona name to frontend
            yield sse_message({'persona_name': persona_name})

            # Bot starts the conversation
            bot_greeting = "Hello, I am a Deutsche Telekom agent. How can I help you with your tariff today?"
            session['conversation_history'].append({"role": "bot", "content": bot_greeting})
            yield sse_message({'role': 'bot', 'content': bot_greeting})

            # Customer's first message (persona-driven, with self-introduction)
            status_msg = f"{persona_name} ({customer_agent.role}) is about to speak (first message)."
            print(f"[SIM] {status_msg}")
            yield sse_message({'status': status_msg})
            customer_task = Task(
                description=f"""You are {persona_name}. {persona_needs}
Start the conversation by introducing yourself by name and expressing your needs and what you are looking for in a new mobile tariff plan. Do NOT provide advice or recommendations. Keep your response concise and natural.""",
                agent=customer_agent
            )
            customer_message = customer_task.execute()
            session['conversation_history'].append({"role": "customer", "content": customer_message})
            yield sse_message({'role': 'customer', 'content': customer_message})

            while True:
                # Observer agent checks if customer has chosen a tariff
                status_msg = "Observer agent is evaluating if the customer has chosen a tariff..."
                print(f"[SIM] {status_msg}")
                yield sse_message({'status': status_msg})
                observer_task = Task(
                    description=f"""Here is the conversation so far:
{format_conversation(session['conversation_history'])}

Has the customer clearly chosen or confirmed a specific Deutsche Telekom tariff plan? If yes, reply with YES and the exact plan name (as mentioned by the customer). If not, reply with NO.""",
                    agent=observer_agent
                )
                observer_response = observer_task.execute().strip()
                if observer_response.upper().startswith("YES"):
                    plan_name = observer_response[3:].strip(': .-')
                    if not plan_name:
                        plan_name = "a tariff plan"
                    # Bot agent sends the final thank you and confirmation message
                    status_msg = f"{bot_agent.role} is sending confirmation for plan: {plan_name}"
                    print(f"[SIM] {status_msg}")
                    yield sse_message({'status': status_msg})
                    confirmation_task = Task(
                        description=f"The customer has confirmed their selection of the {plan_name} plan. Thank them, confirm their choice, and welcome them to the Deutsche Telekom family. This should be your final message.",
                        agent=bot_agent
                    )
                    confirmation_message = confirmation_task.execute()
                    session['conversation_history'].append({"role": "bot", "content": confirmation_message})
                    yield sse_message({'role': 'bot', 'content': confirmation_message})
                    yield sse_message({'end': True})
                    break

                # Bot's response (includes Tarifs.md)
                status_msg = f"{bot_agent.role} is about to respond."
                print(f"[SIM] {status_msg}")
                yield sse_message({'status': status_msg})
                bot_task = Task(
                    description=f"""Here is the conversation so far:
{format_conversation(session['conversation_history'])}

Here are the official Deutsche Telekom tariff plans and options:
{tarifs_md}

As a Telekom Assistant, use only the plans and options above to answer the customer's needs. Ask relevant questions to understand their requirements better. Provide information and recommendations only from the plans and options above. If the customer hasn't made a choice yet, suggest specific plans that match their needs. Keep your response concise and natural.""",
                    agent=bot_agent
                )
                bot_message = bot_task.execute()
                session['conversation_history'].append({"role": "bot", "content": bot_message})
                yield sse_message({'role': 'bot', 'content': bot_message})

                # Customer's response
                status_msg = f"{persona_name} ({customer_agent.role}) is about to speak."
                print(f"[SIM] {status_msg}")
                yield sse_message({'status': status_msg})
                customer_task = Task(
                    description=f"""Here is the conversation so far:
{format_conversation(session['conversation_history'])}

You are {persona_name}. {persona_needs}
Respond ONLY as a real customer. Do NOT provide advice, recommendations, or information as if you were an advisor or bot. Focus on expressing your own needs, preferences, or questions. If you want to choose a plan, clearly state which plan you want to select. Keep your response concise and natural.""",
                    agent=customer_agent
                )
                customer_message = customer_task.execute()
                session['conversation_history'].append({"role": "customer", "content": customer_message})
                yield sse_message({'role': 'customer', 'content': customer_message})

            # Save conversation to JSON
            conversation_data = {
                "timestamp": datetime.now().isoformat(),
                "persona": persona_name,
                "conversation": session['conversation_history']
            }
            save_conversation(session_id, conversation_data)
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            yield sse_message({'error': str(e)})

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/user_message', methods=['POST'])
def user_message():
    """Handle user input mode: receive user message, respond with bot agent only."""
    try:
        data = request.get_json()
        session_id = data.get('session_id', '')
        if not session_id:
            return jsonify({'error': 'No session ID provided'}), 400

        session = session_manager.get_session(session_id)
        session_manager.update_activity(session_id)

        user_message = data.get('message', '').strip()
        conversation_history = session['conversation_history']
        
        if not user_message:
            return jsonify({'error': 'No message provided.'}), 400

        # Get bot response
        tarifs_md = read_tariffs()
        bot_task = Task(
            description=f"""The customer said: {user_message}

Here are the official Deutsche Telekom tariff plans and options:
{tarifs_md}

As a Telekom Assistant, respond to the customer's needs and questions. Provide information and recommendations only from the plans and options above. Keep your response concise and natural.""",
            agent=bot_agent
        )
        bot_message = bot_task.execute()

        # Check if customer has chosen a tariff using observer agent
        observer_task = Task(
            description=f"""Here is the conversation so far:
{format_conversation(conversation_history + [{"role": "customer", "content": user_message}, {"role": "bot", "content": bot_message}])}

Has the customer clearly chosen or confirmed a specific Deutsche Telekom tariff plan? If yes, reply with YES and the exact plan name (as mentioned by the customer). If not, reply with NO.""",
            agent=observer_agent
        )
        observer_response = observer_task.execute().strip()
        conversation_complete = observer_response.upper().startswith("YES")
        
        # If a tariff was selected, get the final thank you message
        if conversation_complete:
            selected_plan = observer_response[3:].strip(': .-')  # Extract plan name after "YES"
            if not selected_plan:
                selected_plan = "the selected tariff"  # Fallback if plan name not found
            
            final_message_task = Task(
                description=f"""The customer has confirmed their selection of the {selected_plan} plan. 
Send a final thank you message that:
1. Thanks them for choosing the specific plan
2. Welcomes them to the Deutsche Telekom family
3. Keeps the message concise and friendly""",
                agent=bot_agent
            )
            bot_message = final_message_task.execute()

        # Update conversation history
        conversation_history.append({"role": "customer", "content": user_message})
        conversation_history.append({"role": "bot", "content": bot_message})
        session['conversation_history'] = conversation_history

        # Save conversation to JSON if complete
        if conversation_complete:
            conversation_data = {
                "timestamp": datetime.now().isoformat(),
                "conversation": conversation_history
            }
            save_conversation(session_id, conversation_data)

        return jsonify({
            'content': bot_message,
            'conversation_complete': conversation_complete
        })
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, threaded=True) 