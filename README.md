# Deutsche Telekom Tariff Simulator

## Project Background

This project was created as part of a B2B hackathon where I served as a jury member evaluating participants and selecting winners. The simulator was developed to test and demonstrate the capabilities of modern agentic frameworks in a practical business context. As a jury member, I wanted to gain hands-on experience with the technologies being evaluated to better understand their potential applications and limitations.

The simulator demonstrates how AI agents can be used to create realistic, goal-oriented conversations between customers and service representatives, helping customers find the most suitable tariff plan based on their needs while maximizing revenue for Deutsche Telekom.

## Features

- **Dual Mode Operation**:
  - **Simulator Mode**: Automatically generates conversations between AI personas and the Telekom assistant
  - **User Input Mode**: Allows direct interaction with the Telekom assistant

- **Smart Conversation Management**:
  - Real-time conversation simulation
  - Automatic detection of tariff selection
  - Personalized thank you messages
  - Conversation history tracking
  - Session-based state management for multiple browser windows

- **Modern User Interface**:
  - Clean, responsive design
  - Real-time status updates
  - Loading indicators
  - Conversation download functionality
  - Markdown support in messages

## Technical Stack

- **Backend**:
  - Flask (Python web framework)
  - CrewAI for agent management
  - LMStudio for LLM integration (optimized for Mistral models)
  - Server-Sent Events (SSE) for real-time updates

- **Frontend**:
  - HTML5/CSS3
  - Vanilla JavaScript
  - Marked.js for Markdown rendering

## Architecture & Decision Making Process

### Multi-Agent Architecture

The simulator uses a multi-agent architecture with three specialized agents:

1. **Telekom Agent**: The primary agent that interacts with customers, understands their needs, and recommends appropriate tariff plans. This agent is designed to balance customer satisfaction with revenue maximization.

2. **Customer Agent**: Simulates realistic customer behavior with various personas and needs. This agent progresses the conversation naturally and avoids repetitive responses.

3. **Terminator Agent**: A specialized decision-making agent that determines when a customer has explicitly chosen a tariff plan. This agent uses extremely strict criteria to ensure the conversation only ends when a clear selection has been made. It immediately rejects any message containing a question mark as a plan selection, ensuring customers can ask questions without triggering the end of the conversation.

### Conversation Flow

The conversation follows a structured flow:

1. **Initial Engagement**: The Telekom Agent presents 2-3 options that match the customer's initial needs.

2. **Progressive Narrowing**: As the conversation continues, the agent narrows down to one best plan that matches all stated requirements.

3. **Decision Point**: The Terminator Agent continuously evaluates if the customer has made a clear selection using strict criteria. It checks for question marks, explicit purchase language, and specific plan naming to ensure only genuine selections are detected.

4. **Confirmation**: When a selection is detected, a personalized confirmation message is generated.

### LLM Integration

The simulator is optimized for use with **LM Studio** and **Mistral models**. When selecting a model, consider these guidelines:

- **Recommended Models**: Mistral-7B-Instruct-v0.3 (currently configured in .env), Mistral-7B-Instruct-v0.2, or other instruction-tuned Mistral variants
- **Model Requirements**: The model must be capable of following complex instructions and maintaining context across multiple turns
- **Performance Considerations**: Larger models (7B+) generally perform better for this task

> **Important**: Choose a model that is specifically instruction-tuned. Models without instruction tuning may not properly follow the agent task descriptions and could generate inconsistent responses.

## Setup Instructions

1. **Prerequisites**:
   - Python 3.8 or higher
   - LMStudio running locally on port 1234
   - Required Python packages (install via `pip install -r requirements.txt`):
     - flask
     - crewai
     - langchain
     - requests

2. **Local Environment Setup**:
   - Create a virtual environment:
     ```bash
     python -m venv venv
     ```
   - Activate the virtual environment:
     - On Windows:
       ```bash
       .\venv\Scripts\activate
       ```
     - On macOS/Linux:
       ```bash
       source venv/bin/activate
       ```
   - Install dependencies:
     ```bash
     pip install -r requirements.txt
     ```

3. **Installation**:
   ```bash
   git clone [repository-url]
   cd [repository-name]
   pip install -r requirements.txt
   ```

4. **Configuration**:
   - Ensure LMStudio is running on `http://localhost:1234` with an appropriate Mistral model loaded
   - Place your tariff data in `Tarifs.md`
   - Configure personas in `personas.py`
   - Set up your `.env` file (see below)

### About the .env File

The project includes a `.env` file in the repository that has been intentionally removed from `.gitignore`. This is done to make it easier for others to run the simulator without configuration and to transparently show all settings used in the project.

The `.env` file contains:
- LMStudio API endpoint configuration (`http://127.0.0.1:1234/v1`)
- The specific Mistral model being used (`mistral-7b-instruct-v0.3`)
- File paths for tariffs and conversation history
- Maximum conversation turns

> **Note**: While including `.env` files in repositories is generally not recommended for production applications with sensitive data, this project contains no sensitive information and is intended for educational/demonstration purposes only.

5. **Running the Application**:
   ```bash
   python app.py
   ```
   The application will be available at `http://localhost:5000`

## Usage

### Simulator Mode
1. Select "Simulator Mode"
2. Click "Start Simulation"
3. Watch as the AI personas interact with the Telekom assistant
4. Download the conversation when complete

### User Input Mode
1. Select "User Input Mode"
2. Type your message in the input field
3. Press Enter or click Send
4. Continue the conversation until you select a tariff
5. Download the conversation when complete

## Project Structure

```
├── app.py                 # Main Flask application with routing and agent orchestration
├── prompts.py            # Centralized prompt templates for all agents
├── personas.py           # Customer personas with diverse needs and preferences
├── Tarifs.md             # Tariff plan data and descriptions
├── .env                  # Environment configuration (LM Studio settings, etc.)
├── requirements.txt      # Python dependencies
├── conversation_history/ # Stored conversations
├── static/
│   ├── css/
│   │   └── styles.css    # Centralized CSS styles for the application
│   └── js/
│       └── script.js     # Centralized JavaScript functionality
└── templates/
    └── index.html        # Frontend interface with real-time updates
```

### Code Organization

- **Modular Backend Design**: The backend codebase is organized with a clean separation of concerns:
  - Agent definitions and orchestration in app.py
  - All prompt templates centralized in prompts.py
  - Customer personas defined in personas.py
  - Tariff data stored in Tarifs.md

- **Prompt Management**: All agent prompts are stored in a dedicated prompts.py file for easier maintenance and updates. This includes:
  - Telekom Agent prompts for customer assistance
  - Customer Agent prompts for simulating realistic behavior
  - Terminator Agent prompts for detecting plan selections
  - System prompts for LLM interactions

- **Frontend Organization**: The frontend follows best practices for web development:
  - HTML structure in templates/index.html
  - CSS styles extracted to static/css/styles.css
  - JavaScript functionality in static/js/script.js
  - Clean separation of structure, presentation, and behavior

- **Improved Maintainability**: Each technology now lives in its own file:
  - Changes to styling can be made without touching HTML or JavaScript
  - UI behavior can be modified independently of structure
  - Code is more readable with proper separation of concerns

## Features in Detail

### Session Management
- Each browser window maintains its own session
- Conversations are isolated between windows
- Automatic session cleanup after 30 minutes of inactivity

### Conversation Storage
- Conversations are saved in the `conversation_history` directory
- Each conversation is stored in a separate JSON file
- Files are named with session IDs for easy tracking

### Real-time Updates
- Server-Sent Events (SSE) for live conversation updates
- Status bar shows current operation
- Loading indicators for long operations
