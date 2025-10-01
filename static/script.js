// WebSocket connection
const socket = io();

// Connection status management
socket.on('connect', function() {
    updateConnectionStatus('connected', 'Connected');
    showNotification('Connected to smart home system', 'success');
});

socket.on('disconnect', function() {
    updateConnectionStatus('disconnected', 'Disconnected');
    showNotification('Disconnected from server', 'error');
});

socket.on('reconnect', function() {
    updateConnectionStatus('connected', 'Reconnected');
    showNotification('Reconnected to server', 'success');
});

// Handle light state updates
socket.on('light_changed', function(data) {
    updateLightIndicator(data.room, data.state, data.source);
    updateLastUpdate();
});

// Update connection status UI
function updateConnectionStatus(status, text) {
    const statusElement = document.getElementById('connection-status');
    statusElement.className = `connection-status status-${status}`;
    statusElement.querySelector('.status-text').textContent = text;
    
    const statusDot = statusElement.querySelector('.status-dot');
    if (status === 'connected') {
        statusDot.style.animation = 'pulse 2s infinite';
    } else {
        statusDot.style.animation = 'none';
    }
}

// Update light indicator
function updateLightIndicator(room, state, source) {
    const indicator = document.getElementById(`${room}-indicator`);
    const card = document.getElementById(`${room}-card`);
    const statusText = indicator.querySelector('.status-text');
    const lightBulb = indicator.querySelector('.light-bulb i');
    
    if (state) {
        card.classList.add('room-active');
        statusText.textContent = 'ON';
        lightBulb.className = 'fas fa-lightbulb';
    } else {
        card.classList.remove('room-active');
        statusText.textContent = 'OFF';
        lightBulb.className = 'fas fa-lightbulb';
    }
    
    // Show notification for automation events
    if (source === 'automation') {
        showNotification(`🤖 ${room} light turned ${state ? 'on' : 'off'} automatically`, 'info');
    } else if (source === 'chatbot') {
        showNotification(`💬 ${room} light controlled via assistant`, 'info');
    }
}

// Control individual light
function controlLight(room, state) {
    fetch(`/api/light/${room}/${state ? 'on' : 'off'}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showNotification(`Error: ${data.error}`, 'error');
        }
    })
    .catch(error => {
        console.error('Error controlling light:', error);
        showNotification('Error controlling light', 'error');
    });
}

// Control all lights
function controlAllLights(state) {
    const action = state ? 'on' : 'off';
    fetch(`/api/light/all/${action}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showNotification(`Error: ${data.error}`, 'error');
        } else {
            showNotification(`All lights turned ${action}`, 'success');
        }
    })
    .catch(error => {
        console.error('Error controlling all lights:', error);
        showNotification('Error controlling lights', 'error');
    });
}

// Chat functionality
function sendMessage() {
    const input = document.getElementById('message-input');
    const message = input.value.trim();
    
    if (message) {
        addMessage(message, 'user');
        input.value = '';
        
        // Disable input while processing
        input.disabled = true;
        
        fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ message: message })
        })
        .then(response => response.json())
        .then(data => {
            addMessage(data.response, 'bot');
            input.disabled = false;
            input.focus();
        })
        .catch(error => {
            console.error('Chat error:', error);
            addMessage('Sorry, I encountered an error. Please try again.', 'bot');
            input.disabled = false;
            input.focus();
        });
    }
}

function addMessage(text, sender) {
    const messages = document.getElementById('chat-messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}-message`;
    
    const now = new Date();
    const timeString = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    
    messageDiv.innerHTML = `
        <div class="message-avatar">
            <i class="fas ${sender === 'user' ? 'fa-user' : 'fa-robot'}"></i>
        </div>
        <div class="message-content">
            <div class="message-text">${formatMessage(text)}</div>
            <div class="message-time">${timeString}</div>
        </div>
    `;
    
    messages.appendChild(messageDiv);
    messages.scrollTop = messages.scrollHeight;
}

function formatMessage(text) {
    // Convert line breaks to <br> tags
    text = text.replace(/\n/g, '<br>');
    
    // Format emoji shortcuts
    const emojiMap = {
        '✅': '✅',
        '❌': '❌',
        '💡': '💡',
        '🔍': '🔍',
        '📊': '📊',
        '🏠': '🏠',
        '🌙': '🌙',
        '👋': '👋',
        '🎬': '🎬',
        '🎉': '🎉',
        '🤖': '🤖',
        '💬': '💬'
    };
    
    Object.keys(emojiMap).forEach(emoji => {
        text = text.replace(new RegExp(emoji, 'g'), emojiMap[emoji]);
    });
    
    return text;
}

function quickCommand(command) {
    const input = document.getElementById('message-input');
    input.value = command;
    sendMessage();
}

function clearChat() {
    const messages = document.getElementById('chat-messages');
    messages.innerHTML = `
        <div class="message bot-message">
            <div class="message-avatar">
                <i class="fas fa-robot"></i>
            </div>
            <div class="message-content">
                <div class="message-text">
                    Chat cleared. How can I help you with your smart home?
                </div>
                <div class="message-time">Just now</div>
            </div>
        </div>
    `;
}

// Notification system
function showNotification(message, type = 'info') {
    const notification = document.getElementById('notification');
    const icon = type === 'error' ? 'fa-exclamation-circle' : 
                 type === 'warning' ? 'fa-exclamation-triangle' : 
                 type === 'success' ? 'fa-check-circle' : 'fa-info-circle';
    
    notification.innerHTML = `
        <i class="fas ${icon}"></i>
        <span>${message}</span>
    `;
    notification.className = `notification-toast show ${type}`;
    
    setTimeout(() => {
        notification.classList.remove('show');
    }, 4000);
}

// Update last update time
function updateLastUpdate() {
    const now = new Date();
    const timeString = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    document.getElementById('last-update').textContent = `Last update: ${timeString}`;
}

// Keyboard shortcuts
document.addEventListener('keydown', function(e) {
    const input = document.getElementById('message-input');
    
    // Ctrl + / to focus chat input
    if (e.ctrlKey && e.key === '/') {
        e.preventDefault();
        input.focus();
    }
    
    // Enter to send message when input is focused
    if (e.key === 'Enter' && document.activeElement === input) {
        sendMessage();
    }
});

// Auto-focus chat input on page load
document.addEventListener('DOMContentLoaded', function() {
    // You can auto-focus the chat input if desired
    // document.getElementById('message-input').focus();
    
    // Initial status update
    updateLastUpdate();
    
    // Load initial light states
    fetch('/api/lights/status')
        .then(response => response.json())
        .then(status => {
            for (const [room, state] of Object.entries(status)) {
                updateLightIndicator(room, state, 'system');
            }
        })
        .catch(error => {
            console.error('Error fetching initial status:', error);
        });
});

// Periodic status update (every 30 seconds)
setInterval(updateLastUpdate, 30000);