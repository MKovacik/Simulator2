# Telecom Tariff Simulator

A web application that simulates conversations between customers and a Deutsche Telekom assistant, helping customers find the most suitable tariff plan based on their needs.

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
  - LMStudio for LLM integration
  - Server-Sent Events (SSE) for real-time updates

- **Frontend**:
  - HTML5/CSS3
  - Vanilla JavaScript
  - Marked.js for Markdown rendering

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
   - Ensure LMStudio is running on `http://localhost:1234`
   - Place your tariff data in `Tarifs.md`
   - Configure personas in `personas.py`

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
├── app.py                 # Main Flask application
├── Tarifs.md             # Tariff data
├── personas.py           # Customer personas
├── requirements.txt      # Python dependencies
├── conversation_history/ # Stored conversations
└── templates/
    └── index.html        # Frontend interface
```

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
