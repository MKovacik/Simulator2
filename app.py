"""
Deutsche Telekom Tariff Simulator Backend
-------------------------------
Flask app using CrewAI to simulate a conversation between a Deutsche Telekom customer (random persona) and a Deutsche Telekom bot, with real tariff data from Tarifs.md.
"""

import os
import json
import time
import uuid
import random
import requests
import threading
from datetime import datetime
from typing import Any, List, Optional, Dict
from flask import Flask, render_template, jsonify, Response, request, stream_with_context
from crewai import Agent, Task, Crew, Process
from langchain.llms.base import LLM
from prompts import (
    TELEKOM_TASK_PROMPT,
    CUSTOMER_TASK_PROMPT,
    TERMINATOR_TASK_PROMPT,
    TERMINATOR_USER_TASK_PROMPT,
    TERMINATOR_LAST_EXCHANGE_PROMPT,
    CONFIRMATION_TASK_PROMPT,
    CUSTOMER_INTRO_PROMPT,
    TELEKOM_SYSTEM_PROMPT,
    GENERAL_SYSTEM_PROMPT,
    SIMPLE_SYSTEM_PROMPT
)
from personas import PERSONAS
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# === Constants ===
TARIFFS_FILE = os.getenv('TARIFFS_FILE', 'Tarifs.md')
CONVERSATION_HISTORY_DIR = os.getenv('CONVERSATION_HISTORY_DIR', 'conversation_history')
SESSION_MAX_AGE_MINUTES = int(os.getenv('SESSION_MAX_AGE_MINUTES', '30'))
MAX_TURNS = 10

# === Flask App ===
app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Disable caching
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Ensure conversation history directory exists
os.makedirs(CONVERSATION_HISTORY_DIR, exist_ok=True)

# === Helper function to execute tasks with timeout monitoring but no fallbacks
def execute_task_with_retry(task, max_retries=1, timeout=60):
    """Execute a task with retry logic and timeout monitoring.
    
    This function will wait for the task to complete, regardless of timeout.
    The timeout parameter is only used for logging purposes.
    """
    for attempt in range(max_retries + 1):
        try:
            # Use a monitoring mechanism to log long-running tasks
            result = None
            start_time = time.time()
            
            def execute_task():
                nonlocal result
                try:
                    result = task.execute()
                except Exception as e:
                    print(f"Task execution error: {str(e)}")
                    result = None
            
            # Create and start the execution thread
            execution_thread = threading.Thread(target=execute_task)
            execution_thread.daemon = True
            execution_thread.start()
            
            # Check periodically if the task is taking too long
            while execution_thread.is_alive():
                execution_thread.join(timeout/4)  # Check every quarter of the timeout period
                
                if execution_thread.is_alive():
                    elapsed = time.time() - start_time
                    if elapsed > timeout:
                        print(f"Task execution taking longer than expected: {elapsed:.1f} seconds so far")
                        # We don't return a fallback - just keep waiting
            
            if result is not None:
                elapsed = time.time() - start_time
                print(f"Task completed in {elapsed:.1f} seconds")
                return result
            raise Exception("Task execution failed with no result")
            
        except Exception as e:
            if attempt < max_retries:
                print(f"Task execution failed, retrying... ({attempt+1}/{max_retries})")
                time.sleep(1)  # Short delay before retry
            else:
                print(f"Task execution failed after {max_retries} retries: {str(e)}")
                raise  # Re-raise the exception instead of returning a fallback

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

# === LLM Wrapper ===
class LMStudioLLM(LLM):
    """LLM wrapper for LMStudio API."""
    # Define these as class attributes for Pydantic
    base_url: str = "http://localhost:1234/v1"
    model_name: str = "mistral-7b-instruct-v0.3"
    
    def __init__(self):
        # Force reload from environment variables every time
        super().__init__()
        # Update the values from environment variables
        self.base_url = os.getenv('LMSTUDIO_BASE_URL', 'http://localhost:1234/v1')
        self.model_name = os.getenv('LMSTUDIO_MODEL_NAME', 'mistral-7b-instruct-v0.3')
        print(f"Initialized LMStudioLLM with model: {self.model_name}\nBase URL: {self.base_url}")

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        try:
            # Check if this is a CrewAI task execution
            is_crewai_task = "Thought:" in prompt or "Action:" in prompt
            is_telekom_bot = "Deutsche Telekom Tariff Recommendation Bot" in prompt
            
            # Set parameters based on task type - use higher temperature for more natural responses
            temperature = 0.7  # Standard temperature for natural responses
            max_tokens = -1    # No token limit to allow full responses
        
            
            # Create appropriate system prompt based on task type - specifically for CrewAI format
            if is_crewai_task:
                if is_telekom_bot:
                    system_prompt = TELEKOM_SYSTEM_PROMPT
                else:
                    system_prompt = GENERAL_SYSTEM_PROMPT
            else:
                system_prompt = SIMPLE_SYSTEM_PROMPT
            
            # Log the start time for performance monitoring
            start_time = time.time()
            print(f"Sending request to LMStudio API for model: {self.model_name}")
            
            # Prepare request payload - handle models that don't support system role
            # For Mistral in LM Studio, we need to combine system prompt with user message
            combined_prompt = prompt
            if system_prompt:
                combined_prompt = f"{system_prompt}\n\n{prompt}"
                
            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "user", "content": combined_prompt}
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False
            }
            
            # Ensure the base_url has the correct format
            api_url = self.base_url
            if not api_url.endswith('/'):
                api_url += '/'
            if not api_url.endswith('v1/'):
                api_url += 'v1/'
            
            # Construct the full endpoint URL
            endpoint_url = f"{api_url}chat/completions"
            
            # Log the request details for debugging
            print(f"Request URL: {endpoint_url}")
            print(f"Request payload: {json.dumps(payload, indent=2)}")
            
            # Make the API call without a timeout
            try:
                response = requests.post(
                    endpoint_url,
                    json=payload
                )
                
                # Check if the response is valid JSON
                try:
                    response_json = response.json()
                    print(f"Response status: {response.status_code}")
                    
                    if response.status_code != 200:
                        print(f"Error response: {json.dumps(response_json, indent=2)}")
                        raise Exception(f"API returned error: {response.status_code} - {response_json.get('error', 'Unknown error')}")
                    
                    content = response_json["choices"][0]["message"]["content"]
                    
                    # Log completion time
                    elapsed = time.time() - start_time
                    print(f"LMStudio API response received in {elapsed:.2f} seconds")
                    
                except ValueError as json_err:
                    print(f"Failed to parse JSON response: {str(json_err)}")
                    print(f"Raw response: {response.text[:500]}...")
                    raise Exception(f"Invalid JSON response from API: {str(json_err)}")
                    
            except requests.exceptions.RequestException as req_err:
                print(f"Request failed: {str(req_err)}")
                raise Exception(f"Request to LMStudio API failed: {str(req_err)}")
                
            # Ensure we have valid content
            if not content:
                raise Exception("Empty response content from API")
            
            # Enhanced format handling for CrewAI responses - simplified for better compatibility
            if is_crewai_task:
                # Extract the actual response content, regardless of format
                actual_content = content
                
                # If there's a Final Answer section, extract that as the main content
                if "Final Answer:" in content:
                    final_answer_parts = content.split("Final Answer:", 1)
                    if len(final_answer_parts) > 1:
                        actual_content = final_answer_parts[1].strip()
                
                # Create a properly formatted response for CrewAI
                # This exact format is what CrewAI expects
                content = f"Thought: Do I need to use a tool? No\nFinal Answer: {actual_content}"
                
                # Log the formatted response
                print(f"Formatted response for CrewAI:\n{content}")
            
            return content
        except requests.exceptions.RequestException as e:
            print(f"Error calling LMStudio API: {str(e)}")
            # Re-raise the exception instead of providing a fallback
            raise Exception(f"Failed to get response from LMStudio: {str(e)}")

    @property
    def _llm_type(self) -> str:
        return "lmstudio"

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {"base_url": self.base_url, "model_name": self.model_name}

# === Helper Functions ===
def read_tariffs(file_path: str = TARIFFS_FILE) -> str:
    """Read the tariffs Markdown file."""
    if not os.path.exists(file_path):
        return "Tariff data not available."
    with open(file_path, 'r', encoding='utf-8') as f:
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
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(conversation_data, f, indent=2)

def get_last_exchange(history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Get the last exchange (last customer message and bot response) from conversation history."""
    if len(history) >= 2:
        return history[-2:]
    return history

# === Agents ===
llm = LMStudioLLM()

def create_agents():
    """Create and return the agents for the conversation."""
    customer_agent = Agent(
        role='Deutsche Telekom Customer',
        goal='Express needs and requirements for a new mobile tariff plan',
        backstory="""You are a real customer looking for a new mobile tariff plan. \
You have specific needs regarding data usage, international calls, and budget constraints.\
You should ask questions and express concerns naturally. Do NOT provide advice, recommendations, or information as if you were an advisor or bot. Only talk about your own needs, preferences, and questions as a customer would.""",
        llm=llm,
        verbose=True,
        allow_delegation=False
    )

    telekom_bot = Agent(
        role='Deutsche Telekom Agent',
        goal='Help customers find the right tariff plan while maximizing revenue',
        backstory="You are a skilled Deutsche Telekom agent who excels at understanding customer needs and recommending appropriate mobile tariff plans. You always listen carefully to customer requests and address their specific questions. While your primary goal is customer satisfaction, you also aim to maximize revenue by suggesting beneficial add-ons and premium features that match customer requirements. Only recommend plans from the Tarifs.md file. Be responsive, helpful, and attentive to customer needs.",
        llm=llm,
        verbose=True,
        allow_delegation=False
    )

    terminator_agent = Agent(
        role='Terminator Agent',
        goal='Determine if the customer has selected a plan',
        backstory="You analyze customer messages to determine if they have explicitly chosen a tariff plan. You are extremely strict about what counts as a selection. If a selection is made, you identify the exact plan name.",
        llm=llm,
        verbose=True,
        allow_delegation=False
    )
    
    return customer_agent, telekom_bot, terminator_agent

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
            
            # Create agents for this conversation
            customer_agent, telekom_bot, terminator_agent = create_agents()

            # First customer message
            status_msg = f"{persona_name} (Customer) is about to speak (first message)."
            print(f"[SIM] {status_msg}")
            yield sse_message({'status': status_msg})
            
            # Create the first customer task
            customer_task = Task(
                description=CUSTOMER_INTRO_PROMPT.format(
                    persona_name=persona_name,
                    persona_needs=persona_needs
                ),
                agent=customer_agent,
                expected_output="A natural customer introduction and expression of needs"
            )
            
            # Execute the first customer task directly
            customer_message = customer_task.execute()
            session['conversation_history'].append({"role": "customer", "content": customer_message})
            yield sse_message({'role': 'customer', 'content': customer_message})

            # Main conversation loop
            for turn in range(MAX_TURNS):
                # Create a shared context for this turn
                shared_context = {
                    "conversation_history": format_conversation(session['conversation_history']),
                    "tariffs": tarifs_md,
                    "persona": f"{persona_name}. {persona_needs}",
                    "turn": turn + 1
                }

                # Bot response
                status_msg = "Telekom Agent: Preparing response..."
                print(f"[SIM] {status_msg}")
                yield sse_message({'status': status_msg})

                # Calculate conversation turn number
                turn_number = len([msg for msg in session['conversation_history'] if msg['role'] == 'customer'])
                
                bot_task = Task(
                    description=TELEKOM_TASK_PROMPT.format(
                        conversation_history=format_conversation(session['conversation_history']),
                        tariffs=tarifs_md,
                        persona=f"{persona_name}. {persona_needs}"
                    ),
                    agent=telekom_bot,
                    expected_output="Responsive, helpful recommendation that addresses the customer's specific questions and needs"
                )
                
                # Get the previous customer messages to check for repetition
                prev_customer_msgs = [msg['content'] for msg in session['conversation_history'] if msg['role'] == 'customer']
                
                # Execute the bot task with monitoring but no timeout fallback
                status_msg = "Telekom Agent: Analyzing customer needs and generating response..."
                print(f"[SIM] {status_msg}")
                yield sse_message({'status': status_msg})
                
                bot_message = execute_task_with_retry(bot_task, max_retries=1, timeout=120)
                session['conversation_history'].append({"role": "bot", "content": bot_message})
                yield sse_message({'role': 'bot', 'content': bot_message})
                
                # Now create the customer task with the bot message
                customer_task = Task(
                    description=CUSTOMER_TASK_PROMPT.format(
                        persona_name=persona_name,
                        persona_needs=persona_needs,
                        conversation_history=format_conversation(session['conversation_history']),
                        bot_message=bot_message,
                        prev_customer_msgs=prev_customer_msgs[-2:] if len(prev_customer_msgs) >= 2 else []
                    ),
                    agent=customer_agent,
                    expected_output="A single, natural customer response under 100 words that progresses the conversation"
                )
                
                # Observer task to check if customer has chosen a plan
                # This task will be executed after the customer responds
                # We'll update its description with the actual customer message later
                
                # Execute tasks directly with timeout handling
                # Execute bot task with timeout
                status_msg = "Telekom Agent: Generating response (with timeout protection)..."
                print(f"[SIM] {status_msg}")
                yield sse_message({'status': status_msg})
                
                # Bot task has already been executed above
                
                # Execute customer task with monitoring
                status_msg = "Customer is responding (this may take a minute)..."
                print(f"[SIM] {status_msg}")
                yield sse_message({'status': status_msg})
                
                # Execute the customer task with monitoring but no timeout fallback
                customer_message = execute_task_with_retry(customer_task, max_retries=1, timeout=120)
                
                # Add customer message to conversation history
                session['conversation_history'].append({"role": "customer", "content": customer_message})
                yield sse_message({'role': 'customer', 'content': customer_message})
                
                # Check if customer has chosen a plan
                status_msg = "Terminator Agent: Checking if customer has selected a plan..."
                print(f"[SIM] {status_msg}")
                yield sse_message({'status': status_msg})
                
                # Create the terminator task with the actual customer message
                terminator_task = Task(
                    description=TERMINATOR_USER_TASK_PROMPT.format(
                        user_message=customer_message
                    ),
                    agent=terminator_agent,
                    expected_output="YES: [plan name] or NO"
                )
                
                # Use our monitoring mechanism for the terminator task without timeout fallback
                terminator_response = execute_task_with_retry(terminator_task, max_retries=1, timeout=60)
                
                # Check if the customer has chosen a plan
                if terminator_response.upper().startswith("YES:"):
                    plan_name = terminator_response[4:].strip()
                    if not plan_name:
                        plan_name = "a tariff plan"
                        
                    status_msg = f"Telekom Agent: Preparing confirmation for selected plan: {plan_name}"
                    print(f"[SIM] {status_msg}")
                    yield sse_message({'status': status_msg})
                    
                    # Create a final confirmation task
                    confirmation_task = Task(
                        description=CONFIRMATION_TASK_PROMPT.format(plan_name=plan_name),
                        agent=telekom_bot,
                        expected_output="Brief welcome message and next steps under 50 words"
                    )
                    
                    # Execute the confirmation task with monitoring but no timeout fallback
                    status_msg = "Telekom Agent: Generating welcome message for new customer..."
                    print(f"[SIM] {status_msg}")
                    yield sse_message({'status': status_msg})
                    confirmation_message = execute_task_with_retry(confirmation_task, max_retries=1, timeout=60)
                    session['conversation_history'].append({"role": "bot", "content": confirmation_message})
                    yield sse_message({'role': 'bot', 'content': confirmation_message})
                    yield sse_message({'end': True})
                    break

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

        # Create agents for this conversation
        customer_agent, telekom_bot, terminator_agent = create_agents()
        
        # Read tariffs
        tarifs_md = read_tariffs()
        
        # Create shared context
        shared_context = {
            "conversation_history": format_conversation(conversation_history),
            "tariffs": tarifs_md,
            "user_message": user_message
        }
        
        # Create bot response task with optimized description for faster responses
        bot_task = Task(
            description=TELEKOM_TASK_PROMPT.format(
                conversation_history=format_conversation(conversation_history),
                tariffs=tarifs_md,
                persona=f"Customer message: {user_message}"
            ),
            agent=telekom_bot,
            expected_output="Brief, helpful response under 100 words"
        )
        
        # Create customer agent task to simulate a follow-up response
        customer_task = Task(
            description=CUSTOMER_TASK_PROMPT.format(
                persona_name="Customer",
                persona_needs="",
                conversation_history=format_conversation(conversation_history),
                bot_message="",  # Not used in this context
                prev_customer_msgs=[user_message]
            ),
            agent=customer_agent,
            expected_output="A single, natural customer response under 100 words",
            # No dependency needed as we don't execute this task
        )
        
        # Create a crew for the bot response
        bot_crew = Crew(
            agents=[telekom_bot, customer_agent],
            tasks=[bot_task, customer_task],
            process=Process.sequential,
            verbose=True,
            shared_context=shared_context
        )
        
        # Execute bot task with monitoring but no timeout fallback
        status_msg = "Telekom Agent: Analyzing customer needs and generating response..."
        print(f"[USER_MSG] {status_msg}")
        
        # Use our monitoring mechanism for the bot task without timeout fallback
        bot_message = execute_task_with_retry(bot_task, max_retries=1, timeout=120)
        
        # We don't need to execute the customer_task in the user_message flow
        # It's only there to simulate a follow-up response in the background

        # Check if the customer has chosen a plan
        last_exchange = get_last_exchange(conversation_history + [
            {"role": "customer", "content": user_message},
            {"role": "bot", "content": bot_message}
        ])
        
        # Create observer task to check if the customer has chosen a plan in their message
        terminator_task = Task(
            description=TERMINATOR_USER_TASK_PROMPT.format(
                user_message=user_message
            ),
            agent=terminator_agent,
            expected_output="YES: [plan name] or NO"
        )
        
        # Execute the observer task with monitoring but no timeout fallback
        status_msg = "Terminator Agent: Analyzing message for plan selection..."
        print(f"[USER_MSG] {status_msg}")
        terminator_response = execute_task_with_retry(terminator_task, max_retries=1, timeout=60)
            
        conversation_complete = terminator_response.upper().startswith("YES:")

        # If conversation is complete, send a final thank you message
        if conversation_complete:
            selected_plan = terminator_response[4:].strip()
            if not selected_plan:
                selected_plan = "the selected tariff"

            # Create a final confirmation task
            final_message_task = Task(
                description=CONFIRMATION_TASK_PROMPT.format(plan_name=selected_plan),
                agent=telekom_bot,
                expected_output="Brief thank you and confirmation under 50 words"
            )
            
            # Execute the final message task with monitoring but no timeout fallback
            status_msg = "Generating final confirmation message..."
            print(f"[USER_MSG] {status_msg}")
            final_message = execute_task_with_retry(final_message_task, max_retries=1, timeout=60)
            
            bot_message = final_message

        # Update conversation history
        conversation_history.append({"role": "customer", "content": user_message})
        conversation_history.append({"role": "bot", "content": bot_message})
        session['conversation_history'] = conversation_history

        # Save conversation if complete
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
    port = int(os.getenv('PORT', 5000))
    host = os.getenv('HOST', '0.0.0.0')
    debug = os.getenv('FLASK_DEBUG', '1') == '1'
    app.run(host=host, port=port, debug=debug, threaded=True) 