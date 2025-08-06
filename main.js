document.addEventListener('DOMContentLoaded', () => {
    const conversationLog = document.getElementById('conversation-log');
    const promptInput = document.getElementById('prompt-input');
    const sendBtn = document.getElementById('send-prompt');
    const sessionList = document.getElementById('session-list');
    const loadSessionBtn = document.getElementById('load-session-btn');
    const saveSessionNameInput = document.getElementById('save-session-name');
    const saveSessionBtn = document.getElementById('save-session-btn');
    const deleteSessionBtn = document.getElementById('delete-session-btn');
    const themeToggleBtn = document.getElementById('theme-toggle');
    const sessionNameDisplay = document.getElementById('session-name-display');
    const orchestratorStatus = document.getElementById('orchestrator-status');
    const orchestratorText = document.getElementById('orchestrator-text');
    const agentStatus = document.getElementById('agent-status');
    const agentText = document.getElementById('agent-text');

    const SERVER_URL = window.location.origin;
    const socket = io(SERVER_URL);
    let currentSessionName = '[New Session]';

    const logClientEvent = (eventName, details = {}, destination = "Server", control_flow = null) => {
        socket.emit('log_audit_event', { 
            event: eventName, 
            details: details,
            source: "Client",
            destination: destination,
            control_flow: control_flow
        });
    };
    
    const userIcon = `<svg class="w-5 h-5 mr-2 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20"><path d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z"></path></svg>`;
    const agentIcon = `<svg class="w-5 h-5 mr-2 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20"><path d="M10 12a2 2 0 100-4 2 2 0 000 4z" /><path fill-rule="evenodd" d="M.458 10C3.732 4.943 9.5 3 10 3s6.268 1.943 9.542 7c-3.274 5.057-9.5 7-9.542 7S3.732 15.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clip-rule="evenodd" /></svg>`;
    const gearIcon = `<svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.532 1.532 0 012.287-.947c1.372.836 2.942-.734-2.106-2.106a1.532 1.532 0 01-.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd"></path></svg>`;
    
    const addConversationLog = (message, type) => {
        const trimmedMessage = message ? message.trim() : '';
        if (!trimmedMessage || !type) {
            return;
        }
        logClientEvent("addConversationLog()", {"type": type, "message": message}, "Client", null);
        if (type === 'tool_result') {
            const entry = document.createElement('div');
            entry.className = 'tool-result-entry';
            entry.innerHTML = `<div>${gearIcon}<span>${trimmedMessage}</span></div>`;
            conversationLog.appendChild(entry);
            conversationLog.scrollTop = conversationLog.scrollHeight;
            return;
        }
        let formattedMessage = marked.parse(trimmedMessage, { gfm: true, breaks: true });
        let typeDisplay, icon, titleHTML;
        switch(type) {
            case 'user': typeDisplay = 'You'; icon = userIcon; break;
            case 'final_answer': typeDisplay = currentSessionName; icon = agentIcon; break;
            case 'info': typeDisplay = currentSessionName; icon = agentIcon; break;
            case 'system_confirm_replayed': typeDisplay = currentSessionName; icon = agentIcon; break;
            case 'system_confirm': typeDisplay = currentSessionName; icon = agentIcon; break;
        }
        titleHTML = `<strong class="text-white/80">${typeDisplay}:</strong>`;
        const content = `<div class="flex items-start">${icon}<div class="flex-1">${titleHTML}<div class="mt-1 text-sm message-body">${formattedMessage}</div></div></div>`;
        const entry = document.createElement('div');
        entry.className = `log-entry log-entry-${type}`;
        entry.innerHTML = content;
        conversationLog.appendChild(entry);
        conversationLog.scrollTop = conversationLog.scrollHeight;

        if (type === 'system_confirm') {
            promptInput.disabled = true; 
            sendBtn.disabled = true;

            const buttonContainer = document.createElement('div');
            buttonContainer.className = 'mt-4 flex space-x-2';

            const yesBtn = document.createElement('button');
            yesBtn.textContent = 'Yes';
            yesBtn.className = 'bg-green-600 hover:bg-green-700 text-white font-bold py-1 px-4 rounded-md text-sm transition-colors';
            yesBtn.onclick = () => {
                handleConfirmation('yes');
                buttonContainer.remove();
            };

            const noBtn = document.createElement('button');
            noBtn.textContent = 'No';
            noBtn.className = 'bg-red-600 hover:bg-red-700 text-white font-bold py-1 px-4 rounded-md text-sm transition-colors';
            noBtn.onclick = () => {
                handleConfirmation('no');
                buttonContainer.remove();
            };

            buttonContainer.appendChild(yesBtn);
            buttonContainer.appendChild(noBtn);

            const messageBody = entry.querySelector('.message-body');
            if (messageBody) {
                messageBody.appendChild(buttonContainer);
            } else {
                entry.appendChild(buttonContainer);
            }
            conversationLog.scrollTop = conversationLog.scrollHeight;
        }
    };

    const addToolLog = (message) => {
        logClientEvent("addToolLog()", {"message": message}, "Client", null);
        const entry = document.createElement('div');
        entry.className = 'tool-log-entry';
        entry.textContent = message;
        conversationLog.appendChild(entry);
        conversationLog.scrollTop = conversationLog.scrollHeight;
    };

    const requestSessionList = () => { 
        logClientEvent("Socket.IO Emit: request_session_list", {}, "Server", "Request");
        if (socket.connected) socket.emit('request_session_list'); 
    };

    socket.on('connect', () => {
        logClientEvent("Socket.IO Event Received: connect", {}, "Client", null);
        orchestratorStatus.className = 'w-3 h-3 rounded-full bg-green-500'; orchestratorText.textContent = 'Orchestrator Online';
        agentStatus.className = 'w-3 h-3 rounded-full bg-green-500'; agentText.textContent = 'Agent Online';
        requestSessionList(); 
        logClientEvent("Socket.IO Emit: request_session_name", {}, "Client", "Request");
        socket.emit('request_session_name');
    });

    socket.on('disconnect', () => {
        logClientEvent("Socket.IO Event Received: disconnect", {}, "Client", null);
        orchestratorStatus.className = 'w-3 h-3 rounded-full bg-red-500 animate-pulse'; orchestratorText.textContent = 'Orchestrator Offline';
        agentStatus.className = 'w-3 h-3 rounded-full bg-red-500 animate-pulse'; agentText.textContent = 'Agent Offline';
    });
    
    socket.on('log_message', (msg) => {
        logClientEvent("Socket.IO Event Received: log_message", {"msg": msg}, "Client", null);
        addConversationLog(msg.data, msg.type);
    });
    
    socket.on('display_user_prompt', (data) => {
        logClientEvent("Socket.IO Event Received: display_user_prompt", {"data": data}, "Client", null);
        addConversationLog(data.prompt, 'user');
    });

    socket.on('tool_log', (msg) => {
        logClientEvent("Socket.IO Event Received: tool_log", {"msg": msg}, "Client", null);
        addToolLog(msg.data);
    });

    socket.on('request_user_confirmation', (data) => {
        logClientEvent("Socket.IO Event Received: request_user_confirmation", {"data": data}, "Client", null);
        if (!data || !data.prompt) {
            console.error("Confirmation request received with invalid data:", data);
            return;
        }
        addConversationLog(data.prompt, 'system_confirm');
    });

    socket.on('session_list_update', (result) => {
        logClientEvent("Socket.IO Event Received: session_list_update", {"result": result}, "Client", null);
        sessionList.innerHTML = '';
        const placeholder = new Option('Choose session...', '', true, true); placeholder.disabled = true; sessionList.add(placeholder);
        if (result?.status === 'success' && result.content) { result.content.forEach(session => { sessionList.add(new Option(session.name, session.name)); }); }
    });

    socket.on('session_name_update', (data) => {
        logClientEvent("Socket.IO Event Received: session_name_update", {"data": data}, "Client", null);
        currentSessionName = data.name || '[New Session]';
        sessionNameDisplay.textContent = currentSessionName;
    });

    socket.on('clear_chat_history', () => {
        logClientEvent("Socket.IO Event Received: clear_chat_history", {}, "Client", null);
        conversationLog.innerHTML = '';
    });

    const handleUserPrompt = () => {
        logClientEvent("Event Handler Triggered: handleUserPrompt()", {}, "Client", null);
        const prompt = promptInput.value.trim();
        if (!prompt) return;
        promptInput.value = '';
        adjustTextareaHeight();
        const payload = { prompt };
        logClientEvent("Socket.IO Emit: start_task", {"payload": payload}, "Server", null);
        socket.emit('start_task', payload);
    };

    const handleSaveSession = () => {
        logClientEvent("Event Handler Triggered: handleSaveSession()", {}, "Client", null);
        const name = saveSessionNameInput.value.trim();
        if (!name) return alert("Please enter a name for the session.");
        const payload = { prompt: `save this session as \\"${name}\\"` };
        logClientEvent("Socket.IO Emit: start_task", {"payload": payload}, "Server", null);
        socket.emit('start_task', payload);
        saveSessionNameInput.value = '';
    };

    const handleLoadSession = () => {
        logClientEvent("Event Handler Triggered: handleLoadSession()", {}, "Client", null);
        if (!sessionList.value) return alert("Please select a session to load.");
        const payload = { prompt: `Please load the session named \\"${sessionList.value}\\"` };
        logClientEvent("Socket.IO Emit: start_task", {"payload": payload}, "Server", null);
        socket.emit('start_task', payload);
    };

    const handleDeleteSession = () => {
        logClientEvent("Event Handler Triggered: handleDeleteSession()", {}, "Client", null);
        if (!sessionList.value) return alert("Please select a session to delete.");
        const payload = { prompt: `delete the session named \\"${sessionList.value}\\"` };
        logClientEvent("Socket.IO Emit: start_task", {"payload": payload}, "Server", null);
        socket.emit('start_task', payload);
    };

    const handleConfirmation = (response) => {
        logClientEvent("Event Handler Triggered: handleConfirmation()", {"response": response}, "Client", null);
        const payload = { response };
        logClientEvent("Socket.IO Emit: user_confirmation", {"payload": payload}, "Server", null);
        socket.emit('user_confirmation', payload);
        promptInput.disabled = false; sendBtn.disabled = false; promptInput.focus();
    };

    const setupTheme = () => {
        if (localStorage.theme === 'dark' || (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
            document.documentElement.classList.add('dark');
        } else {
            document.documentElement.classList.remove('dark');
        }
        const isDark = document.documentElement.classList.contains('dark');
        document.getElementById('theme-icon-dark').classList.toggle('hidden', !isDark);
        document.getElementById('theme-icon-light').classList.toggle('hidden', isDark);
    };

    const toggleTheme = () => {
        logClientEvent("Event Handler Triggered: toggleTheme", {}, "Client", null);
        document.documentElement.classList.toggle('dark');
        localStorage.theme = document.documentElement.classList.contains('dark') ? 'dark' : 'light';
        setupTheme();
    };

    const adjustTextareaHeight = () => {
        promptInput.style.height = 'auto';
        promptInput.style.height = `${promptInput.scrollHeight}px`;
        if (promptInput.scrollHeight > parseFloat(getComputedStyle(promptInput).maxHeight)) { promptInput.style.overflowY = 'auto';
        } else { promptInput.style.overflowY = 'hidden'; }
    };

    sendBtn.addEventListener('click', handleUserPrompt);
    promptInput.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleUserPrompt(); } });
    promptInput.addEventListener('input', adjustTextareaHeight);
    saveSessionBtn.addEventListener('click', handleSaveSession);
    loadSessionBtn.addEventListener('click', handleLoadSession);
    deleteSessionBtn.addEventListener('click', handleDeleteSession);
    themeToggleBtn.addEventListener('click', toggleTheme);
    
    setupTheme(); adjustTextareaHeight();
});
