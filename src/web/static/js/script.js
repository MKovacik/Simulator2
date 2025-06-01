 // Initialize elements object
let elements = {};

// Function to cache DOM elements after the DOM is fully loaded
function initializeElements() {
    elements = {
        simulateBtn: document.getElementById('simulateBtn'),
        loadingSpinner: document.getElementById('loadingSpinner'),
        conversation: document.getElementById('conversation'),
        downloadBtn: document.getElementById('downloadBtn'),
        simulatorMode: document.getElementById('simulatorMode'),
        userMode: document.getElementById('userMode'),
        userModeOption: document.querySelector('.mode-option[onclick="setMode(\'user\')"]'),
        userInputArea: document.getElementById('userInputArea'),
        userInput: document.getElementById('userInput'),
        sendBtn: document.getElementById('sendBtn'),
        statusBar: document.getElementById('statusBar'),
        modeDescription: document.getElementById('modeDescription'),
        logToggleBtn: document.getElementById('logToggleBtn')
    };
}

// State management using sessionStorage
const state = {
    get conversationHistory() {
        return JSON.parse(sessionStorage.getItem('conversationHistory') || '[]');
    },
    set conversationHistory(value) {
        sessionStorage.setItem('conversationHistory', JSON.stringify(value));
    },
    get customerName() {
        return sessionStorage.getItem('customerName') || 'Customer';
    },
    set customerName(value) {
        sessionStorage.setItem('customerName', value);
    },
    get simulatorMode() {
        return sessionStorage.getItem('simulatorMode') === 'true';
    },
    set simulatorMode(value) {
        sessionStorage.setItem('simulatorMode', value);
    },
    get simulationRunning() {
        return sessionStorage.getItem('simulationRunning') === 'true';
    },
    set simulationRunning(value) {
        sessionStorage.setItem('simulationRunning', value);
    },
    get showLogs() {
        return sessionStorage.getItem('showLogs') === 'true';
    },
    set showLogs(value) {
        sessionStorage.setItem('showLogs', value);
    }
};

let eventSource = null;

// Debounce function to limit rapid function calls
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Throttle function to limit function execution rate
function throttle(func, limit) {
    let inThrottle;
    return function executedFunction(...args) {
        if (!inThrottle) {
            func(...args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

function setStatusBar(message, type = '') {
    // Parse agent name and action from the message format "Agent: Action..."
    const messageParts = message.match(/^([^:]+):\s*(.+)$/);
    
    if (messageParts) {
        const [_, agentName, action] = messageParts;
        elements.statusBar.innerHTML = `<span class="agent-name">${agentName}</span>: <span class="action">${action}</span>`;
        
        // Also add as a log message to the conversation
        if (state.showLogs) {
            addLogMessage(message, type);
        }
    } else {
        elements.statusBar.textContent = message;
        
        // Also add as a log message to the conversation
        if (state.showLogs) {
            addLogMessage(message, type);
        }
    }
    
    elements.statusBar.className = 'status-bar' + (type ? ' ' + type : '');
}

function addLogMessage(message, type = '') {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message log' + (type ? ' ' + type : '');
    messageDiv.setAttribute('data-log', 'true');
    
    const bubbleDiv = document.createElement('div');
    bubbleDiv.className = 'bubble';
    bubbleDiv.textContent = message;
    
    messageDiv.appendChild(bubbleDiv);
    
    elements.conversation.appendChild(messageDiv);
    scrollToBottom();
}

function toggleLogs() {
    state.showLogs = !state.showLogs;
    
    // Update button text
    elements.logToggleBtn.textContent = state.showLogs ? 'Hide Logs' : 'Show Logs';
    
    // Show/hide existing log messages
    const logMessages = document.querySelectorAll('.message.log');
    logMessages.forEach(msg => {
        msg.style.display = state.showLogs ? 'flex' : 'none';
    });
}

function setMode(mode) {
    state.simulatorMode = mode === 'simulator';
    
    // Update radio buttons
    elements.simulatorMode.checked = state.simulatorMode;
    elements.userMode.checked = !state.simulatorMode;
    
    // Update mode options styling
    document.querySelectorAll('.mode-option').forEach(option => {
        option.classList.remove('active');
    });
    document.querySelector(`.mode-option[onclick="setMode('${mode}')"]`).classList.add('active');
    
    // Update UI elements
    if (state.simulatorMode) {
        elements.userInputArea.style.display = 'none';
        elements.userInput.disabled = true;
        elements.sendBtn.disabled = true;
        elements.simulateBtn.style.display = 'flex';
        elements.modeDescription.textContent = 'Simulator mode will automatically generate a conversation between a customer and the Telekom assistant.';
    } else {
        elements.userInputArea.style.display = 'block';
        elements.userInput.disabled = false;
        elements.sendBtn.disabled = false;
        elements.simulateBtn.style.display = 'none';
        elements.modeDescription.textContent = 'User input mode allows you to chat directly with the Telekom assistant.';
    }
}

function resetSimulationState() {
    elements.simulateBtn.disabled = true;
    elements.simulatorMode.disabled = true;
    elements.userMode.disabled = true;
    elements.userModeOption.style.opacity = '0.5';
    elements.userModeOption.style.cursor = 'not-allowed';
    elements.userModeOption.onclick = null;
    state.simulationRunning = true;
    elements.loadingSpinner.classList.add('active');
    elements.conversation.innerHTML = '';
    state.conversationHistory = [];
    elements.downloadBtn.style.display = 'none';
    state.customerName = 'Customer';
    
    // Initialize log visibility state if not set
    if (state.showLogs === undefined) {
        state.showLogs = true;
        elements.logToggleBtn.textContent = 'Hide Logs';
    }
}

function restoreSimulationState() {
    elements.simulateBtn.disabled = false;
    elements.simulatorMode.disabled = false;
    elements.userMode.disabled = false;
    elements.userModeOption.style.opacity = '1';
    elements.userModeOption.style.cursor = 'pointer';
    elements.userModeOption.onclick = function() { setMode('user'); };
    state.simulationRunning = false;
    elements.loadingSpinner.classList.remove('active');
}

function startSimulation() {
    if (!state.simulatorMode) return;
    
    resetSimulationState();
    setStatusBar('Starting simulation...', '');
    
    // Close existing connection if any
    if (eventSource) {
        eventSource.close();
    }
    
    // Create new SSE connection with unique session ID
    const sessionId = Date.now().toString(36) + Math.random().toString(36).substr(2);
    eventSource = new EventSource(`/simulate?simulator_mode=1&session_id=${sessionId}`);
    
    eventSource.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            if (data.persona_name) {
                state.customerName = data.persona_name;
                setStatusBar('Simulating conversation for ' + state.customerName + '...', '');
                return;
            }
            if (data.status) {
                setStatusBar(data.status, '');
                return;
            }
            if (data.error) {
                handleSimulationError(data.error);
                return;
            }
            if (data.end) {
                handleSimulationEnd();
                return;
            }
            if (data.log) {
                // Handle log messages
                if (state.showLogs) {
                    addLogMessage(data.log, data.log_type || '');
                }
                return;
            }
            addMessage(data.role, data.content);
            const history = state.conversationHistory;
            history.push({role: data.role, content: data.content, timestamp: new Date().toLocaleTimeString()});
            state.conversationHistory = history;
        } catch (error) {
            console.error('Error processing message:', error);
            setStatusBar('Error processing message: ' + error.message, 'error');
        }
    };
    
    eventSource.onerror = function(error) {
        console.error('SSE connection error:', error);
        handleSimulationError('Connection error. Please try again.');
    };
    
    eventSource.onopen = function() {
        console.log('SSE connection opened');
        setStatusBar('Simulation started...', '');
    };
}

function handleSimulationError(error) {
    if (eventSource) {
        eventSource.close();
    }
    elements.conversation.innerHTML = `<div class="message bot"><div class="bubble">Error: ${error}</div></div>`;
    restoreSimulationState();
    setStatusBar('Error: ' + error, 'error');
}

function handleSimulationEnd() {
    if (eventSource) {
        eventSource.close();
    }
    restoreSimulationState();
    setStatusBar('Simulation complete.', 'complete');
    elements.downloadBtn.style.display = 'inline-block';
}

// Throttled scroll to bottom
const scrollToBottom = throttle(() => {
    elements.conversation.scrollTo({ top: elements.conversation.scrollHeight, behavior: 'smooth' });
}, 100);

function addMessage(role, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message ' + (role === 'bot' ? 'bot' : 'customer');
    
    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'avatar';
    avatarDiv.setAttribute('aria-hidden', 'true');
    avatarDiv.innerText = role === 'bot' ? '🤖' : '🧑';
    
    let sanitized = content.trim()
        .replace(/^```[\s\S]*?```$/gm, '')
        .replace(/^```|```$/g, '')
        .trim();
    
    const bubbleDiv = document.createElement('div');
    bubbleDiv.className = 'bubble';
    bubbleDiv.innerHTML = marked.parse(sanitized);
    
    const metaDiv = document.createElement('div');
    metaDiv.className = 'meta';
    metaDiv.innerText = new Date().toLocaleTimeString();
    
    messageDiv.appendChild(avatarDiv);
    messageDiv.appendChild(bubbleDiv);
    messageDiv.appendChild(metaDiv);
    
    if (role !== 'bot') {
        bubbleDiv.innerHTML = `<strong>${state.customerName}</strong><br>` + bubbleDiv.innerHTML;
    } else {
        bubbleDiv.innerHTML = `<strong>Telekom Assistant</strong><br>` + bubbleDiv.innerHTML;
    }
    
    elements.conversation.appendChild(messageDiv);
    scrollToBottom();
}

// Debounced message sending
const debouncedSendMessage = debounce(() => {
    const message = elements.userInput.value.trim();
    if (!message) return;
    
    elements.userInput.disabled = true;
    elements.sendBtn.disabled = true;
    
    addMessage('customer', message);
    const history = state.conversationHistory;
    history.push({role: 'customer', content: message, timestamp: new Date().toLocaleTimeString()});
    state.conversationHistory = history;
    elements.userInput.value = '';
    setStatusBar('Waiting for Telekom Assistant response...', '');
    
    fetch('/user_message', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            message: message,
            conversation_history: history,
            session_id: Date.now().toString(36) + Math.random().toString(36).substr(2)
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            handleUserMessageError(data.error);
        } else {
            handleUserMessageSuccess(data);
        }
    })
    .catch(err => {
        handleUserMessageError(err);
    });
}, 300);

function handleUserMessageError(error) {
    setStatusBar('Error: ' + error, 'error');
    elements.simulateBtn.disabled = false;
    elements.simulatorMode.disabled = false;
    if (state.simulatorMode) {
        state.simulationRunning = false;
    }
    elements.userInput.disabled = false;
    elements.sendBtn.disabled = false;
}

function handleUserMessageSuccess(data) {
    addMessage('bot', data.content);
    const history = state.conversationHistory;
    history.push({role: 'bot', content: data.content, timestamp: new Date().toLocaleTimeString()});
    state.conversationHistory = history;
    
    if (data.conversation_complete) {
        setStatusBar('Thank you for choosing a tariff! The conversation is complete.', 'complete');
        elements.simulateBtn.disabled = false;
        elements.simulatorMode.disabled = false;
        elements.downloadBtn.style.display = 'inline-block';
        elements.userInput.disabled = true;
        elements.sendBtn.disabled = true;
        state.simulationRunning = false;
    } else {
        setStatusBar('You can continue the conversation or end it.', '');
        elements.userInput.disabled = false;
        elements.sendBtn.disabled = false;
        elements.userInput.focus();
    }
}

function sendUserMessage() {
    if (state.simulatorMode && !state.simulationRunning) {
        console.error('Cannot send message: simulation is not running');
        return;
    }
    debouncedSendMessage();
}

function downloadConversation() {
    const history = state.conversationHistory;
    if (!history.length) return;
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(history, null, 2));
    const dlAnchor = document.createElement('a');
    dlAnchor.setAttribute("href", dataStr);
    dlAnchor.setAttribute("download", "conversation.json");
    document.body.appendChild(dlAnchor);
    dlAnchor.click();
    dlAnchor.remove();
}

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    // Initialize DOM elements
    initializeElements();
    
    // Set initial mode
    if (state.simulatorMode === undefined) {
        state.simulatorMode = true;
    }
    setMode(state.simulatorMode ? 'simulator' : 'user');
    
    // Set initial log visibility
    if (state.showLogs === undefined) {
        state.showLogs = true;
    }
    elements.logToggleBtn.textContent = state.showLogs ? 'Hide Logs' : 'Show Logs';
    
    // Restore conversation if exists
    const history = state.conversationHistory;
    if (history && history.length > 0) {
        history.forEach(item => {
            addMessage(item.role, item.content);
        });
        elements.downloadBtn.style.display = 'inline-block';
    }
});