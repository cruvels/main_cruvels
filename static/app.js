document.addEventListener("DOMContentLoaded", () => {
    // -------------------------------------------------------------
    // Core State & Authentication
    // -------------------------------------------------------------
    let authToken = localStorage.getItem("cruvels_auth_token") || "";
    let currentUser = null;
    let currentConversationId = null;
    let userMemoriesList = [];
    let activeMemoryFilter = "all";

    // DOM Elements: Core
    const statusText = document.getElementById("statusText");
    const statusDot = document.querySelector(".status-dot");
    const modelBadge = document.getElementById("modelBadge");
    const embedBadge = document.getElementById("embedBadge");
    const documentList = document.getElementById("documentList");
    const refreshDocsBtn = document.getElementById("refreshDocsBtn");
    const dropZone = document.getElementById("dropZone");
    const fileInput = document.getElementById("fileInput");
    
    // Chat & Viewport
    const chatForm = document.getElementById("chatForm");
    const userQuery = document.getElementById("userQuery");
    const chatMessages = document.getElementById("chatMessages");
    const chatViewport = document.getElementById("chatViewport");
    const welcomeScreen = document.getElementById("welcomeScreen");
    const clearChatBtn = document.getElementById("clearChatBtn");
    const clearKbBtn = document.getElementById("clearKbBtn");
    const samplePrompts = document.getElementById("samplePrompts");
    const refreshSuggestionsBtn = document.getElementById("refreshSuggestionsBtn");
    const promptsTitle = document.getElementById("promptsTitle");

    // Tabs & Views
    const tabQaBtn = document.getElementById("tabQaBtn");
    const tabDraftingBtn = document.getElementById("tabDraftingBtn");
    const tabKnowledgeBtn = document.getElementById("tabKnowledgeBtn");
    const tabMemoryBtn = document.getElementById("tabMemoryBtn");
    const viewQa = document.getElementById("viewQa");
    const viewDrafting = document.getElementById("viewDrafting");
    const viewKnowledge = document.getElementById("viewKnowledge");
    const viewMemory = document.getElementById("viewMemory");

    // Sidebar User & Conversations
    const conversationList = document.getElementById("conversationList");
    const newChatBtn = document.getElementById("newChatBtn");
    const userChipBtn = document.getElementById("userChipBtn");
    const userNameDisplay = document.getElementById("userNameDisplay");
    const userEmailDisplay = document.getElementById("userEmailDisplay");
    const userAvatarBadge = document.getElementById("userAvatarBadge");
    const authActionBtn = document.getElementById("authActionBtn");
    const authActionIcon = document.getElementById("authActionIcon");

    // Sidebar View Toggle Elements
    const sidebarScrollBody = document.getElementById("sidebarScrollBody");
    const sidebarToggleAll = document.getElementById("sidebarToggleAll");
    const sidebarToggleChats = document.getElementById("sidebarToggleChats");
    const sidebarToggleDocs = document.getElementById("sidebarToggleDocs");
    const convCountBadge = document.getElementById("convCountBadge");
    const docCountBadge = document.getElementById("docCountBadge");

    const sidebarToggleBtns = [sidebarToggleAll, sidebarToggleChats, sidebarToggleDocs];
    sidebarToggleBtns.forEach(btn => {
        if (!btn) return;
        btn.addEventListener("click", () => {
            sidebarToggleBtns.forEach(b => b && b.classList.remove("active"));
            btn.classList.add("active");
            const viewMode = btn.getAttribute("data-view") || "all";
            if (sidebarScrollBody) {
                sidebarScrollBody.className = `sidebar-scroll-body view-${viewMode}`;
            }
        });
    });

    // Auth Modal
    const authModal = document.getElementById("authModal");
    const authModalTitle = document.getElementById("authModalTitle");
    const authModalSubtitle = document.getElementById("authModalSubtitle");
    const authForm = document.getElementById("authForm");
    const authNameRow = document.getElementById("authNameRow");
    const authFirstName = document.getElementById("authFirstName");
    const authLastName = document.getElementById("authLastName");
    const authEmail = document.getElementById("authEmail");
    const authPassword = document.getElementById("authPassword");
    const authErrorBanner = document.getElementById("authErrorBanner");
    const authSubmitBtn = document.getElementById("authSubmitBtn");
    const authToggleText = document.getElementById("authToggleText");
    const authToggleLink = document.getElementById("authToggleLink");
    let isRegisterMode = false;

    // Memory Studio Elements
    const autoMemoryToggle = document.getElementById("autoMemoryToggle");
    const openAddMemoryBtn = document.getElementById("openAddMemoryBtn");
    const clearAllMemoriesBtn = document.getElementById("clearAllMemoriesBtn");
    const memoryFilterBar = document.getElementById("memoryFilterBar");
    const memoriesGrid = document.getElementById("memoriesGrid");
    const addMemoryModal = document.getElementById("addMemoryModal");
    const closeAddMemoryBtn = document.getElementById("closeAddMemoryBtn");
    const cancelAddMemoryBtn = document.getElementById("cancelAddMemoryBtn");
    const addMemoryForm = document.getElementById("addMemoryForm");
    const newMemType = document.getElementById("newMemType");
    const newMemContent = document.getElementById("newMemContent");
    const newMemImportance = document.getElementById("newMemImportance");

    // Knowledge Inspector Elements
    const inspectorDocSelect = document.getElementById("inspectorDocSelect");
    const inspectorDocRibbon = document.getElementById("inspectorDocRibbon");
    const entityFilterBar = document.getElementById("entityFilterBar");

    // Drafting Studio Elements
    const draftDocType = document.getElementById("draftDocType");
    const draftInstructions = document.getElementById("draftInstructions");
    const generateDraftBtn = document.getElementById("generateDraftBtn");
    const reanalyzeStyleBtn = document.getElementById("reanalyzeStyleBtn");
    const activeStyleBadge = document.getElementById("activeStyleBadge");
    const draftOutput = document.getElementById("draftOutput");
    const draftResultTitle = document.getElementById("draftResultTitle");
    const validationPanel = document.getElementById("validationPanel");
    const validationNotes = document.getElementById("validationNotes");
    const copyDraftBtn = document.getElementById("copyDraftBtn");

    // -------------------------------------------------------------
    // Authenticated Fetch Wrapper
    // -------------------------------------------------------------
    async function authFetch(url, options = {}) {
        options.headers = options.headers || {};
        if (authToken) {
            if (options.headers instanceof Headers) {
                options.headers.set("Authorization", `Bearer ${authToken}`);
            } else {
                options.headers["Authorization"] = `Bearer ${authToken}`;
            }
        }
        try {
            const res = await fetch(url, options);
            if (res.status === 401) {
                showAuthModal(true);
            }
            return res;
        } catch (err) {
            console.error("Network error in authFetch:", err);
            throw err;
        }
    }

    // Tab switcher
    function switchTab(activeBtn, activeView) {
        [tabQaBtn, tabDraftingBtn, tabKnowledgeBtn, tabMemoryBtn].forEach(b => { if (b) b.classList.remove("active"); });
        [viewQa, viewDrafting, viewKnowledge, viewMemory].forEach(v => { if (v) v.style.display = "none"; });

        if (activeBtn) activeBtn.classList.add("active");
        if (activeView) activeView.style.display = "flex";

        if (activeView === viewKnowledge) {
            openKnowledgeInspectorView();
        } else if (activeView === viewMemory) {
            fetchMemories();
        }
    }

    if (tabQaBtn) tabQaBtn.addEventListener("click", () => switchTab(tabQaBtn, viewQa));
    if (tabDraftingBtn) tabDraftingBtn.addEventListener("click", () => switchTab(tabDraftingBtn, viewDrafting));
    if (tabKnowledgeBtn) tabKnowledgeBtn.addEventListener("click", () => switchTab(tabKnowledgeBtn, viewKnowledge));
    if (tabMemoryBtn) tabMemoryBtn.addEventListener("click", () => switchTab(tabMemoryBtn, viewMemory));

    // -------------------------------------------------------------
    // Authentication Management
    // -------------------------------------------------------------
    function showAuthModal(show = true) {
        if (!authModal) return;
        authModal.style.display = show ? "flex" : "none";
        if (show) {
            authErrorBanner.style.display = "none";
        }
    }

    function setAuthMode(isRegister) {
        isRegisterMode = isRegister;
        if (isRegisterMode) {
            authModalTitle.textContent = "Create Cruvels Account";
            authModalSubtitle.textContent = "Build your personal AI memory and private knowledge base";
            authNameRow.style.display = "flex";
            authSubmitBtn.innerHTML = '<i class="fa-solid fa-user-plus"></i> Create Account';
            authToggleText.textContent = "Already have an account?";
            authToggleLink.textContent = "Sign In";
        } else {
            authModalTitle.textContent = "Sign In to Cruvels AI";
            authModalSubtitle.textContent = "Secure, private legal intelligence & personal AI memory";
            authNameRow.style.display = "none";
            authSubmitBtn.innerHTML = '<i class="fa-solid fa-right-to-bracket"></i> Sign In';
            authToggleText.textContent = "Don't have an account?";
            authToggleLink.textContent = "Create Account";
        }
    }

    if (authToggleLink) {
        authToggleLink.addEventListener("click", (e) => {
            e.preventDefault();
            setAuthMode(!isRegisterMode);
        });
    }

    if (authForm) {
        authForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            authErrorBanner.style.display = "none";
            const email = authEmail.value.trim();
            const password = authPassword.value;
            const firstName = authFirstName.value.trim();
            const lastName = authLastName.value.trim();

            authSubmitBtn.disabled = true;
            authSubmitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Authenticating...';

            try {
                const endpoint = isRegisterMode ? "/api/auth/register" : "/api/auth/login";
                const payload = isRegisterMode
                    ? { email, password, first_name: firstName, last_name: lastName }
                    : { email, password };

                const res = await fetch(endpoint, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload),
                });

                const data = await res.json();
                if (res.ok && data.session_token) {
                    authToken = data.session_token;
                    localStorage.setItem("cruvels_auth_token", authToken);
                    currentUser = data.user;
                    updateUserUI(currentUser);
                    showAuthModal(false);
                    // Refresh data for new authenticated user
                    await initializeUserData();
                } else {
                    authErrorBanner.textContent = data.detail || "Authentication failed. Please verify credentials.";
                    authErrorBanner.style.display = "block";
                }
            } catch (err) {
                authErrorBanner.textContent = "Error connecting to server. Please try again.";
                authErrorBanner.style.display = "block";
            } finally {
                authSubmitBtn.disabled = false;
                setAuthMode(isRegisterMode);
            }
        });
    }

    function updateUserUI(user) {
        if (!user) {
            userNameDisplay.textContent = "Guest User";
            userEmailDisplay.textContent = "Click to Sign In";
            userAvatarBadge.innerHTML = '<i class="fa-solid fa-user"></i>';
            authActionIcon.className = "fa-solid fa-right-to-bracket";
            authActionBtn.title = "Sign In";
            return;
        }

        const fullName = `${user.first_name || ""} ${user.last_name || ""}`.trim() || user.email.split("@")[0];
        userNameDisplay.textContent = fullName;
        userEmailDisplay.textContent = user.email;
        userAvatarBadge.textContent = fullName.charAt(0).toUpperCase();
        authActionIcon.className = "fa-solid fa-arrow-right-from-bracket";
        authActionBtn.title = "Sign Out";
    }

    if (authActionBtn) {
        authActionBtn.addEventListener("click", () => {
            if (authToken) {
                if (confirm("Are you sure you want to sign out?")) {
                    logoutUser();
                }
            } else {
                showAuthModal(true);
            }
        });
    }

    if (userChipBtn) {
        userChipBtn.addEventListener("click", () => {
            if (!authToken) {
                showAuthModal(true);
            } else {
                switchTab(tabMemoryBtn, viewMemory);
            }
        });
    }

    async function logoutUser() {
        try {
            await authFetch("/api/auth/logout", { method: "POST" });
        } catch (e) {}
        authToken = "";
        currentUser = null;
        currentConversationId = null;
        localStorage.removeItem("cruvels_auth_token");
        updateUserUI(null);
        documentList.innerHTML = '<li class="empty-doc">Please log in to view documents</li>';
        conversationList.innerHTML = '<li class="empty-conv">Please log in to view conversations</li>';
        chatMessages.innerHTML = "";
        welcomeScreen.style.display = "flex";
        showAuthModal(true);
    }

    async function checkAuthAndInit() {
        if (!authToken) {
            // First time: prompt login or register
            updateUserUI(null);
            showAuthModal(true);
            return;
        }

        try {
            const res = await authFetch("/api/auth/me");
            if (res.ok) {
                const data = await res.json();
                currentUser = data.user;
                updateUserUI(currentUser);
                if (data.settings && autoMemoryToggle) {
                    autoMemoryToggle.checked = Boolean(data.settings.auto_memory_enabled);
                }
                await initializeUserData();
            } else {
                logoutUser();
            }
        } catch (err) {
            console.error("Auth check failed:", err);
            updateUserUI(null);
        }
    }

    async function initializeUserData() {
        await Promise.all([
            fetchDocuments(),
            fetchConversations(),
            fetchMemories(),
            fetchSuggestions(),
        ]);
    }

    // -------------------------------------------------------------
    // Conversation Management
    // -------------------------------------------------------------
    async function fetchConversations() {
        if (!conversationList) return;
        try {
            const res = await authFetch("/api/conversations");
            if (res.ok) {
                const data = await res.json();
                renderConversations(data.conversations || []);
            }
        } catch (err) {
            console.error("Error fetching conversations:", err);
        }
    }

    function renderConversations(convs) {
        if (!conversationList) return;
        const cBadge = document.getElementById("convCountBadge");
        if (cBadge) cBadge.textContent = convs.length;
        if (convs.length === 0) {
            conversationList.innerHTML = '<li class="empty-conv">No conversations yet</li>';
            return;
        }

        conversationList.innerHTML = convs.map(c => {
            const isActive = c.id === currentConversationId ? "active" : "";
            return `
            <li class="conv-item ${isActive}" data-conv-id="${c.id}" title="${escapeAttribute(c.title)}">
                <span class="conv-name"><i class="fa-regular fa-message"></i> ${escapeHtml(c.title)}</span>
                <button class="conv-delete-btn" data-del-id="${c.id}" title="Delete conversation"><i class="fa-solid fa-trash"></i></button>
            </li>`;
        }).join("");

        conversationList.querySelectorAll(".conv-item").forEach(item => {
            item.addEventListener("click", (e) => {
                if (e.target.closest(".conv-delete-btn")) return;
                const convId = item.getAttribute("data-conv-id");
                if (convId) {
                    selectConversation(convId);
                }
            });
        });

        conversationList.querySelectorAll(".conv-delete-btn").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                e.stopPropagation();
                const convId = btn.getAttribute("data-del-id");
                if (convId && confirm("Delete this conversation?")) {
                    await deleteConversation(convId);
                }
            });
        });
    }

    async function selectConversation(convId) {
        currentConversationId = convId;
        // Highlight in list
        conversationList.querySelectorAll(".conv-item").forEach(item => {
            item.classList.toggle("active", item.getAttribute("data-conv-id") === convId);
        });

        chatMessages.innerHTML = '<div class="prompt-card-loading"><i class="fa-solid fa-spinner fa-spin"></i> Loading messages...</div>';
        welcomeScreen.style.display = "none";

        try {
            const res = await authFetch(`/api/conversations/${convId}/messages`);
            if (res.ok) {
                const data = await res.json();
                const messages = data.messages || [];
                chatMessages.innerHTML = "";
                if (messages.length === 0) {
                    welcomeScreen.style.display = "flex";
                } else {
                    messages.forEach(m => {
                        appendMessage(m.role, m.content, (m.message_metadata && m.message_metadata.sources) || []);
                    });
                }
            }
        } catch (err) {
            console.error("Error loading conversation messages:", err);
            chatMessages.innerHTML = '<div class="inspector-empty-state"><i class="fa-solid fa-triangle-exclamation"></i> Error loading conversation.</div>';
        }
    }

    async function createNewConversation() {
        try {
            const res = await authFetch("/api/conversations", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ title: "New Legal Inquiry" }),
            });
            if (res.ok) {
                const data = await res.json();
                currentConversationId = data.conversation.id;
                chatMessages.innerHTML = "";
                welcomeScreen.style.display = "flex";
                await fetchConversations();
            }
        } catch (err) {
            console.error("Error creating conversation:", err);
        }
    }

    async function deleteConversation(convId) {
        try {
            const res = await authFetch(`/api/conversations/${convId}`, { method: "DELETE" });
            if (res.ok) {
                if (currentConversationId === convId) {
                    currentConversationId = null;
                    chatMessages.innerHTML = "";
                    welcomeScreen.style.display = "flex";
                }
                await fetchConversations();
            }
        } catch (err) {
            console.error("Error deleting conversation:", err);
        }
    }

    if (newChatBtn) {
        newChatBtn.addEventListener("click", () => {
            createNewConversation();
            switchTab(tabQaBtn, viewQa);
        });
    }

    // -------------------------------------------------------------
    // Personal AI Memory Management
    // -------------------------------------------------------------
    async function fetchMemories() {
        if (!memoriesGrid) return;
        try {
            const res = await authFetch("/api/memory");
            if (res.ok) {
                const data = await res.json();
                userMemoriesList = data.memories || [];
                renderMemories(userMemoriesList, activeMemoryFilter);
                updateMemoryCounts(userMemoriesList);
            }
        } catch (err) {
            console.error("Error fetching memories:", err);
        }
    }

    function updateMemoryCounts(mems) {
        const counts = { all: mems.length, PREFERENCE: 0, WRITING_STYLE: 0, PROFILE: 0, WORKFLOW: 0, CONTEXT: 0 };
        mems.forEach(m => {
            const t = (m.memory_type || "CONTEXT").toUpperCase();
            if (counts[t] !== undefined) counts[t]++;
        });

        const setC = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
        setC("memCountAll", counts.all);
        setC("memCountPref", counts.PREFERENCE);
        setC("memCountStyle", counts.WRITING_STYLE);
        setC("memCountProf", counts.PROFILE);
        setC("memCountWork", counts.WORKFLOW);
        setC("memCountCtx", counts.CONTEXT);
    }

    function renderMemories(memories, filterType = "all") {
        if (!memoriesGrid) return;
        const filtered = filterType === "all"
            ? memories
            : memories.filter(m => (m.memory_type || "").toUpperCase() === filterType.toUpperCase());

        if (filtered.length === 0) {
            memoriesGrid.innerHTML = `
                <div class="memory-empty-state">
                    <i class="fa-solid fa-brain"></i>
                    <h4>No Memories in this Category</h4>
                    <p>Add explicit preferences or chat with Cruvels AI to build persistent memories.</p>
                </div>
            `;
            return;
        }

        memoriesGrid.innerHTML = filtered.map(m => {
            const typeKey = (m.memory_type || "context").toLowerCase();
            const dateStr = new Date(m.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
            const impPct = Math.round((Number(m.importance) || 0.5) * 100);

            return `
            <div class="memory-card" data-mem-id="${m.id}">
                <div class="memory-card-top">
                    <span class="memory-type-badge mem-type-${typeKey}">${escapeHtml(m.memory_type)}</span>
                    <span class="badge" style="background: rgba(255,255,255,0.06); font-size: 0.68rem;"><i class="fa-solid fa-star"></i> ${impPct}% Imp</span>
                </div>
                <div class="memory-card-content">
                    ${escapeHtml(m.memory_content)}
                </div>
                <div class="memory-card-footer">
                    <span><i class="fa-regular fa-clock"></i> ${dateStr}</span>
                    <button class="memory-delete-btn" data-del-id="${m.id}" title="Delete memory"><i class="fa-solid fa-trash-can"></i></button>
                </div>
            </div>`;
        }).join("");

        memoriesGrid.querySelectorAll(".memory-delete-btn").forEach(btn => {
            btn.addEventListener("click", async () => {
                const memId = btn.getAttribute("data-del-id");
                if (memId && confirm("Delete this memory? Cruvels AI will no longer retain this rule.")) {
                    await deleteMemory(memId);
                }
            });
        });
    }

    async function deleteMemory(memoryId) {
        try {
            const res = await authFetch(`/api/memory/${memoryId}`, { method: "DELETE" });
            if (res.ok) {
                await fetchMemories();
            }
        } catch (err) {
            console.error("Error deleting memory:", err);
        }
    }

    if (memoryFilterBar) {
        memoryFilterBar.querySelectorAll(".memory-filter-btn").forEach(btn => {
            btn.addEventListener("click", () => {
                memoryFilterBar.querySelectorAll(".memory-filter-btn").forEach(b => b.classList.remove("active"));
                btn.classList.add("active");
                activeMemoryFilter = btn.getAttribute("data-type") || "all";
                renderMemories(userMemoriesList, activeMemoryFilter);
            });
        });
    }

    if (autoMemoryToggle) {
        autoMemoryToggle.addEventListener("change", async () => {
            try {
                await authFetch("/api/memory/settings", {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ auto_memory_enabled: autoMemoryToggle.checked }),
                });
            } catch (err) {
                console.error("Error updating auto memory setting:", err);
            }
        });
    }

    if (clearAllMemoriesBtn) {
        clearAllMemoriesBtn.addEventListener("click", async () => {
            if (confirm("⚠️ Clear ALL personal memories? This removes all personalized rules from your profile.")) {
                try {
                    await authFetch("/api/memory", { method: "DELETE" });
                    await fetchMemories();
                } catch (err) {
                    console.error("Error clearing memories:", err);
                }
            }
        });
    }

    if (openAddMemoryBtn) {
        openAddMemoryBtn.addEventListener("click", () => {
            if (addMemoryModal) addMemoryModal.style.display = "flex";
        });
    }

    if (closeAddMemoryBtn) closeAddMemoryBtn.addEventListener("click", () => addMemoryModal.style.display = "none");
    if (cancelAddMemoryBtn) cancelAddMemoryBtn.addEventListener("click", () => addMemoryModal.style.display = "none");

    if (addMemoryForm) {
        addMemoryForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const mType = newMemType.value;
            const mContent = newMemContent.value.trim();
            const mImp = parseFloat(newMemImportance.value) || 0.7;

            if (!mContent) return;

            try {
                const res = await authFetch("/api/memory", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        memory_type: mType,
                        memory_content: mContent,
                        importance: mImp,
                    }),
                });
                if (res.ok) {
                    newMemContent.value = "";
                    addMemoryModal.style.display = "none";
                    await fetchMemories();
                }
            } catch (err) {
                console.error("Error creating memory:", err);
            }
        });
    }

    // -------------------------------------------------------------
    // Core Application Initialization
    // -------------------------------------------------------------
    checkHealth();
    checkAuthAndInit();

    // Clear Chat Button
    if (clearChatBtn) {
        clearChatBtn.addEventListener("click", () => {
            chatMessages.innerHTML = "";
            welcomeScreen.style.display = "flex";
        });
    }

    if (refreshSuggestionsBtn) {
        refreshSuggestionsBtn.addEventListener("click", fetchSuggestions);
    }

    // Auto-resize textarea
    userQuery.addEventListener("input", () => {
        userQuery.style.height = "auto";
        userQuery.style.height = userQuery.scrollHeight + "px";
    });

    chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const text = userQuery.value.trim();
        if (text) submitQuery(text);
    });

    userQuery.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event("submit"));
        }
    });

    // Upload Handlers
    dropZone.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", () => {
        if (fileInput.files.length > 0) uploadFile(fileInput.files[0]);
    });
    dropZone.addEventListener("dragover", (e) => { e.preventDefault(); dropZone.style.borderColor = "#6366f1"; });
    dropZone.addEventListener("dragleave", () => { dropZone.style.borderColor = "rgba(99, 102, 241, 0.4)"; });
    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.style.borderColor = "rgba(99, 102, 241, 0.4)";
        if (e.dataTransfer.files.length > 0) uploadFile(e.dataTransfer.files[0]);
    });

    if (refreshDocsBtn) refreshDocsBtn.addEventListener("click", fetchDocuments);
    if (clearKbBtn) {
        clearKbBtn.addEventListener("click", () => {
            if (confirm("⚠️ This will permanently delete all your ingested documents and vector embeddings. Continue?")) {
                clearKnowledgeBase();
            }
        });
    }

    async function checkHealth() {
        try {
            const res = await fetch("/api/health");
            if (res.ok) {
                const data = await res.json();
                statusDot.classList.remove("connecting");
                statusText.textContent = "API Ready";
                modelBadge.innerHTML = `<i class="fa-solid fa-brain"></i> ${data.llm_provider} (${data.llm_model})`;
                embedBadge.innerHTML = `<i class="fa-solid fa-vector-square"></i> ${data.embedding_model}`;
            }
        } catch (err) {
            statusDot.classList.add("connecting");
            statusText.textContent = "Server Offline";
        }
    }

    async function fetchDocuments() {
        if (!authToken) return;
        try {
            const res = await authFetch("/api/documents");
            if (res.ok) {
                const data = await res.json();
                const docs = data.documents || [];
                renderDocuments(docs);
                populateInspectorDropdown(docs);
            }
        } catch (err) {
            console.error("Error fetching documents:", err);
        }
    }

    function renderDocuments(docs) {
        const dBadge = document.getElementById("docCountBadge");
        if (dBadge) dBadge.textContent = docs.length;
        if (docs.length === 0) {
            documentList.innerHTML = '<li class="empty-doc">No documents ingested</li>';
            return;
        }
        documentList.innerHTML = docs.map(d => {
            const ext = (d.filename || "").split(".").pop().toUpperCase();
            const iconMap = { PDF: "fa-file-pdf", DOCX: "fa-file-word", TXT: "fa-file-lines", PNG: "fa-file-image", JPG: "fa-file-image", JPEG: "fa-file-image" };
            const icon = iconMap[ext] || "fa-file";
            const docType = (d.document_type || "Other").replace(/_/g, " ");
            const statusClass = d.status === "completed" ? "status-ok" : "status-pending";
            return `
            <li class="doc-item" data-doc-id="${d.document_id}" title="Click to inspect structured knowledge in Explorer">
                <i class="fa-solid ${icon}"></i>
                <div class="doc-info">
                    <span class="doc-name" title="${d.filename}">${d.filename}</span>
                    <span class="doc-meta"><span class="doc-type-badge">${docType}</span> <span class="${statusClass}">${d.status || ""}</span></span>
                </div>
                <i class="fa-solid fa-chevron-right doc-chevron"></i>
            </li>`;
        }).join("");

        documentList.querySelectorAll(".doc-item").forEach(item => {
            item.addEventListener("click", () => {
                const docId = item.getAttribute("data-doc-id");
                if (docId) selectDocumentInInspector(docId, true);
            });
        });
    }

    async function fetchSuggestions() {
        if (!samplePrompts) return;
        samplePrompts.innerHTML = `
            <div class="prompt-card-loading">
                <i class="fa-solid fa-spinner fa-spin"></i>
                <span>Analyzing document and generating suggestions...</span>
            </div>
        `;
        try {
            const res = await authFetch("/api/suggestions");
            if (res.ok) {
                const data = await res.json();
                renderSuggestions(data.suggestions || [], data.is_dynamic);
            } else {
                renderSuggestions([], false);
            }
        } catch (err) {
            renderSuggestions([], false);
        }
    }

    function renderSuggestions(suggestions, isDynamic) {
        if (!samplePrompts) return;
        if (!suggestions || suggestions.length === 0) {
            samplePrompts.innerHTML = `
                <div class="prompt-card-loading">
                    <span>Upload a document to get automated question suggestions.</span>
                </div>
            `;
            return;
        }

        if (promptsTitle) {
            promptsTitle.innerHTML = isDynamic
                ? '<i class="fa-solid fa-wand-magic-sparkles"></i> Tailored Document Suggestions'
                : '<i class="fa-solid fa-file-contract"></i> Recommended Questions';
        }

        samplePrompts.innerHTML = suggestions.map(s => `
            <button class="prompt-card" data-prompt="${escapeAttribute(s.question)}">
                <i class="${s.icon || 'fa-solid fa-file-lines'}"></i>
                <div class="prompt-card-content">
                    <span class="prompt-card-label">${escapeHtml(s.label)}</span>
                    <span class="prompt-card-sub">${escapeHtml(s.question)}</span>
                </div>
            </button>
        `).join("");

        samplePrompts.querySelectorAll(".prompt-card").forEach(card => {
            card.addEventListener("click", () => {
                const promptText = card.getAttribute("data-prompt");
                if (promptText) {
                    userQuery.value = promptText;
                    submitQuery(promptText);
                }
            });
        });
    }

    function escapeHtml(str) {
        if (str === null || str === undefined) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function escapeAttribute(str) {
        if (str === null || str === undefined) return "";
        return String(str).replace(/"/g, "&quot;");
    }

    async function clearKnowledgeBase() {
        clearKbBtn.disabled = true;
        statusText.textContent = "Clearing knowledge base...";
        try {
            const res = await authFetch("/api/knowledge-base", { method: "DELETE" });
            if (res.ok) {
                statusText.textContent = "API Ready";
                await fetchDocuments();
                await fetchSuggestions();
                appendSystemNotice("✅ Knowledge base cleared. All documents and vectors removed.");
            } else {
                statusText.textContent = "API Ready";
                appendSystemNotice("❌ Failed to clear knowledge base.");
            }
        } catch (err) {
            statusText.textContent = "API Ready";
            appendSystemNotice("❌ Network error while clearing knowledge base.");
        } finally {
            clearKbBtn.disabled = false;
        }
    }

    async function uploadFile(file) {
        if (!authToken) {
            showAuthModal(true);
            return;
        }

        const formData = new FormData();
        formData.append("file", file);

        statusText.textContent = "Ingesting " + file.name + "...";
        try {
            const res = await authFetch("/api/documents/upload", {
                method: "POST",
                body: formData,
            });
            fileInput.value = "";
            if (res.ok) {
                const data = await res.json();
                statusText.textContent = "API Ready";
                await fetchDocuments();
                await fetchSuggestions();
                if (data.document_id) {
                    selectDocumentInInspector(data.document_id, false);
                }
                const kuCount = data.knowledge_units || 0;
                const docType = data.document_type || "Document";
                appendSystemNotice(`✅ **${data.filename}** ingested successfully — Type: ${docType} | ${kuCount} knowledge units indexed.`);
            } else {
                statusText.textContent = "API Ready";
                const err = await res.json();
                alert("Upload failed: " + (err.detail || "Error uploading file"));
            }
        } catch (err) {
            statusText.textContent = "API Ready";
            fileInput.value = "";
            alert("Error connecting to server during upload");
        }
    }

    async function submitQuery(question) {
        if (!authToken) {
            showAuthModal(true);
            return;
        }

        welcomeScreen.style.display = "none";
        userQuery.value = "";
        userQuery.style.height = "auto";

        // Auto-create conversation if none selected
        if (!currentConversationId) {
            try {
                const convTitle = question.slice(0, 32) + (question.length > 32 ? "..." : "");
                const cRes = await authFetch("/api/conversations", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ title: convTitle }),
                });
                if (cRes.ok) {
                    const cData = await cRes.json();
                    currentConversationId = cData.conversation.id;
                    fetchConversations();
                }
            } catch (e) {}
        }

        appendMessage("user", question);
        const loadingId = appendLoading();

        try {
            const res = await authFetch("/api/ask", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    question: question,
                    conversation_id: currentConversationId,
                }),
            });

            removeLoading(loadingId);

            if (res.ok) {
                const data = await res.json();
                if (data.conversation_id) {
                    currentConversationId = data.conversation_id;
                }
                appendMessage("assistant", data.answer, data.sources, data.is_fallback);
                // Immediately refresh conversation list so new chat appears in sidebar
                await fetchConversations();
                setTimeout(fetchMemories, 1500);
            } else {
                const err = await res.json();
                appendMessage("assistant", "⚠️ **Error processing request**: " + (err.detail || "Server error"));
            }
        } catch (err) {
            removeLoading(loadingId);
            appendMessage("assistant", "⚠️ **Network Error**: Unable to reach backend server.");
        }
    }

    function appendMessage(role, text, sources = [], isFallback = false) {
        const msgDiv = document.createElement("div");
        msgDiv.className = `message-row ${role}`;

        const avatar = document.createElement("div");
        avatar.className = "avatar";
        avatar.innerHTML = role === "user"
            ? '<i class="fa-solid fa-user"></i>'
            : '<i class="fa-solid fa-scale-balanced"></i>';

        const bubble = document.createElement("div");
        bubble.className = "message-bubble";

        let html = marked.parse(text);
        if (role === "assistant" && isFallback) {
            html = `<div class="fallback-badge"><i class="fa-solid fa-triangle-exclamation"></i> Low confidence: Generalized legal reasoning</div>` + html;
        }

        bubble.innerHTML = html;

        if (sources && sources.length > 0) {
            const sourcesDiv = document.createElement("div");
            sourcesDiv.className = "sources-container";
            sourcesDiv.innerHTML = `
                <div class="sources-title"><i class="fa-solid fa-book-bookmark"></i> Verifiable Document Sources:</div>
                <div class="source-chips">
                    ${sources.map(s => `
                        <div class="source-chip" title="Verified source excerpt">
                            <i class="fa-solid fa-file-contract"></i>
                            <span>${escapeHtml(s.file_name || s.filename || "Doc")} (p.${s.page_number || 1})</span>
                        </div>
                    `).join("")}
                </div>
            `;
            bubble.appendChild(sourcesDiv);
        }

        msgDiv.appendChild(avatar);
        msgDiv.appendChild(bubble);
        chatMessages.appendChild(msgDiv);
        chatViewport.scrollTop = chatViewport.scrollHeight;
    }

    function appendLoading() {
        const id = "loading-" + Date.now();
        const msgDiv = document.createElement("div");
        msgDiv.className = "message-row assistant";
        msgDiv.id = id;

        msgDiv.innerHTML = `
            <div class="avatar"><i class="fa-solid fa-scale-balanced"></i></div>
            <div class="message-bubble loading-bubble">
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
            </div>
        `;
        chatMessages.appendChild(msgDiv);
        chatViewport.scrollTop = chatViewport.scrollHeight;
        return id;
    }

    function removeLoading(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    function appendSystemNotice(mdText) {
        const noticeDiv = document.createElement("div");
        noticeDiv.className = "system-notice";
        noticeDiv.innerHTML = marked.parse(mdText);
        chatMessages.appendChild(noticeDiv);
        chatViewport.scrollTop = chatViewport.scrollHeight;
    }

    // -------------------------------------------------------------
    // Drafting & Style Studio Module
    // -------------------------------------------------------------
    if (generateDraftBtn) {
        generateDraftBtn.addEventListener("click", async () => {
            const docType = draftDocType.value;
            const instructions = draftInstructions.value.trim();

            if (!instructions) {
                alert("Please provide instructions or a drafting goal.");
                return;
            }

            generateDraftBtn.disabled = true;
            generateDraftBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Generating Grounded Draft...';
            draftOutput.innerHTML = '<div class="draft-placeholder"><i class="fa-solid fa-spinner fa-spin"></i><p>Synthesizing legal document with style profile &amp; verified claims...</p></div>';
            validationPanel.style.display = "none";

            try {
                const res = await authFetch("/api/drafting/generate", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        document_type: docType,
                        instructions: instructions,
                    }),
                });

                if (res.ok) {
                    const data = await res.json();
                    draftResultTitle.innerHTML = `<i class="fa-solid fa-file-signature"></i> ${escapeHtml(data.title || "Generated Legal Draft")}`;
                    draftOutput.innerHTML = marked.parse(data.content);

                    if (data.validation_notes && data.validation_notes.length > 0) {
                        validationPanel.style.display = "block";
                        validationNotes.innerHTML = data.validation_notes.map(n => `<div class="validation-item"><i class="fa-solid fa-check"></i> ${escapeHtml(n)}</div>`).join("");
                    }
                } else {
                    const err = await res.json();
                    draftOutput.innerHTML = `<div class="draft-error-card"><i class="fa-solid fa-triangle-exclamation"></i><strong>Drafting Service Error</strong><p>${escapeHtml(err.detail || "Error generating draft")}</p></div>`;
                }
            } catch (err) {
                draftOutput.innerHTML = `<div class="draft-error-card"><i class="fa-solid fa-circle-xmark"></i><strong>Network Error</strong><p>${escapeHtml(err.message)}</p></div>`;
            } finally {
                generateDraftBtn.disabled = false;
                generateDraftBtn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Generate Grounded Draft';
            }
        });
    }

    if (copyDraftBtn) {
        copyDraftBtn.addEventListener("click", () => {
            const text = draftOutput.innerText;
            navigator.clipboard.writeText(text);
            copyDraftBtn.innerHTML = '<i class="fa-solid fa-check"></i> Copied!';
            setTimeout(() => copyDraftBtn.innerHTML = '<i class="fa-solid fa-copy"></i> Copy', 2000);
        });
    }

    // -------------------------------------------------------------
    // Structured Knowledge Inspector Module
    // -------------------------------------------------------------
    let cachedInspectorDocs = [];
    let currentLoadedDocId = null;
    let currentEntitiesCache = [];
    let activeEntityFilter = "all";
    let inspectorLoadSequence = 0;

    const ENTITY_CONFIG = {
        person: { icon: "fa-user", label: "Person", cls: "ent-person" },
        company: { icon: "fa-building", label: "Company", cls: "ent-company" },
        organization: { icon: "fa-sitemap", label: "Organization", cls: "ent-organization" },
        court: { icon: "fa-gavel", label: "Court", cls: "ent-court" },
        judge: { icon: "fa-scale-unbalanced", label: "Judge", cls: "ent-judge" },
        date: { icon: "fa-calendar-day", label: "Date", cls: "ent-date" },
        amount: { icon: "fa-money-bill-wave", label: "Amount", cls: "ent-amount" },
        location: { icon: "fa-location-dot", label: "Location", cls: "ent-location" },
        statute: { icon: "fa-book-bookmark", label: "Statute", cls: "ent-statute" },
        section: { icon: "fa-hashtag", label: "Section", cls: "ent-section" },
        party: { icon: "fa-users-line", label: "Party", cls: "ent-party" },
        case: { icon: "fa-folder-open", label: "Case", cls: "ent-case" },
    };

    const CONCEPT_ICONS = {
        termination: "fa-ban",
        arbitration: "fa-handshake-angle",
        jurisdiction: "fa-map-pin",
        confidentiality: "fa-user-secret",
        indemnity: "fa-shield-halved",
        breach: "fa-triangle-exclamation",
        damages: "fa-coins",
        "governing law": "fa-scale-balanced",
        "intellectual property": "fa-lightbulb",
        liability: "fa-hand-holding-dollar",
        severability: "fa-scissors",
    };

    function renderInspectorDocRibbon(docs, activeDocId) {
        if (!inspectorDocRibbon) return;
        if (!docs || docs.length === 0) {
            inspectorDocRibbon.innerHTML = "";
            return;
        }

        inspectorDocRibbon.innerHTML = docs.map(d => {
            const isActive = d.document_id === activeDocId ? "active" : "";
            const docType = (d.document_type || "Document").replace(/_/g, " ");
            return `
            <div class="inspector-doc-pill ${isActive}" data-doc-id="${escapeAttribute(d.document_id)}" title="Inspect ${escapeAttribute(d.filename)}">
                <i class="fa-solid fa-file-contract"></i>
                <span class="pill-name">${escapeHtml(d.filename)}</span>
                <span class="pill-tag">${escapeHtml(docType)}</span>
            </div>`;
        }).join("");

        inspectorDocRibbon.querySelectorAll(".inspector-doc-pill").forEach(pill => {
            pill.addEventListener("click", () => {
                const docId = pill.getAttribute("data-doc-id");
                if (docId) selectDocumentInInspector(docId, false);
            });
        });
    }

    function populateInspectorDropdown(docs) {
        cachedInspectorDocs = docs || [];
        if (!inspectorDocSelect) return;

        if (cachedInspectorDocs.length === 0) {
            inspectorDocSelect.innerHTML = '<option value="">No documents available. Upload one to begin.</option>';
            inspectorDocSelect.disabled = true;
            if (inspectorDocRibbon) inspectorDocRibbon.innerHTML = "";
            return;
        }

        const prevVal = inspectorDocSelect.value;
        inspectorDocSelect.disabled = false;
        inspectorDocSelect.innerHTML = cachedInspectorDocs.map(d => {
            const docType = (d.document_type || "Document").replace(/_/g, " ");
            return `<option value="${escapeAttribute(d.document_id)}">${escapeHtml(d.filename)} &mdash; [${escapeHtml(docType)}]</option>`;
        }).join("");

        let activeId = prevVal;
        if (!activeId || !cachedInspectorDocs.some(d => d.document_id === activeId)) {
            activeId = cachedInspectorDocs[0].document_id;
        }
        inspectorDocSelect.value = activeId;
        renderInspectorDocRibbon(cachedInspectorDocs, activeId);

        if (!currentLoadedDocId) {
            selectDocumentInInspector(activeId, false);
        }
    }

    if (inspectorDocSelect) {
        inspectorDocSelect.addEventListener("change", (e) => {
            const docId = e.target.value;
            if (docId) selectDocumentInInspector(docId, false);
        });
    }

    function selectDocumentInInspector(docId, shouldSwitchTab = false) {
        if (!docId) return;

        if (inspectorDocSelect && inspectorDocSelect.value !== docId) {
            inspectorDocSelect.value = docId;
        }

        if (inspectorDocRibbon) {
            inspectorDocRibbon.querySelectorAll(".inspector-doc-pill").forEach(pill => {
                pill.classList.toggle("active", pill.getAttribute("data-doc-id") === docId);
            });
        }

        if (documentList) {
            documentList.querySelectorAll(".doc-item").forEach(item => {
                item.classList.toggle("active", item.getAttribute("data-doc-id") === docId);
            });
        }

        if (shouldSwitchTab) {
            switchTab(tabKnowledgeBtn, viewKnowledge);
        }

        loadDocumentKnowledge(docId);
    }

    function openKnowledgeInspectorView() {
        const targetDocId = (inspectorDocSelect && inspectorDocSelect.value) ||
            (cachedInspectorDocs[0] ? cachedInspectorDocs[0].document_id : null);

        if (targetDocId && targetDocId !== currentLoadedDocId) {
            selectDocumentInInspector(targetDocId, false);
        }
    }

    function renderEntityChips(entities, filterType = "all") {
        const entitiesEl = document.getElementById("inspectorEntities");
        if (!entitiesEl) return;

        const filtered = filterType === "all"
            ? entities
            : entities.filter(e => (e.entity_type || "").toLowerCase() === filterType.toLowerCase());

        if (filtered.length === 0) {
            entitiesEl.innerHTML = `<div class="inspector-empty-state"><i class="fa-solid fa-tags"></i><span>No entities found matching filter "${escapeHtml(filterType)}".</span></div>`;
            return;
        }

        entitiesEl.innerHTML = filtered.map(e => {
            const typeKey = (e.entity_type || "other").toLowerCase();
            const conf = ENTITY_CONFIG[typeKey] || { icon: "fa-tag", label: typeKey.toUpperCase(), cls: "ent-other" };
            const confPercent = Math.round((Number(e.confidence) || 0.9) * 100);
            const contextText = e.context || e.name || "";

            return `
            <span class="entity-chip ${conf.cls}" title="Context: ${escapeAttribute(contextText)}">
                <span class="entity-chip-type"><i class="fa-solid ${conf.icon}"></i> ${escapeHtml(conf.label)}</span>
                <span class="entity-chip-name">${escapeHtml(e.name || "")}</span>
                <span class="entity-chip-conf">${confPercent}%</span>
            </span>`;
        }).join("");
    }

    function renderEntityFilters(entities) {
        if (!entityFilterBar) return;
        if (!entities || entities.length === 0) {
            entityFilterBar.style.display = "none";
            return;
        }

        const typeCounts = {};
        entities.forEach(e => {
            const t = (e.entity_type || "other").toLowerCase();
            typeCounts[t] = (typeCounts[t] || 0) + 1;
        });

        const types = Object.keys(typeCounts);
        if (types.length <= 1) {
            entityFilterBar.style.display = "none";
            return;
        }

        entityFilterBar.style.display = "flex";
        let filterHtml = `<button class="entity-filter-btn ${activeEntityFilter === 'all' ? 'active' : ''}" data-filter="all">All (${entities.length})</button>`;

        types.forEach(t => {
            const conf = ENTITY_CONFIG[t] || { label: t.toUpperCase() };
            const isActive = activeEntityFilter === t ? 'active' : '';
            filterHtml += `<button class="entity-filter-btn ${isActive}" data-filter="${escapeAttribute(t)}">${escapeHtml(conf.label)} (${typeCounts[t]})</button>`;
        });

        entityFilterBar.innerHTML = filterHtml;

        entityFilterBar.querySelectorAll(".entity-filter-btn").forEach(btn => {
            btn.addEventListener("click", () => {
                entityFilterBar.querySelectorAll(".entity-filter-btn").forEach(b => b.classList.remove("active"));
                btn.classList.add("active");
                activeEntityFilter = btn.getAttribute("data-filter");
                renderEntityChips(currentEntitiesCache, activeEntityFilter);
            });
        });
    }

    async function loadDocumentKnowledge(documentId) {
        if (!documentId) return;

        const seq = ++inspectorLoadSequence;
        currentLoadedDocId = documentId;

        const sectionsEl = document.getElementById("inspectorSections");
        const entitiesEl = document.getElementById("inspectorEntities");
        const conceptsEl = document.getElementById("inspectorConcepts");
        const claimsEl = document.getElementById("inspectorClaims");

        const countSecEl = document.getElementById("countSections");
        const countEntEl = document.getElementById("countEntities");
        const countConcEl = document.getElementById("countConcepts");
        const countClmEl = document.getElementById("countClaims");

        const statSecEl = document.getElementById("statSecCount");
        const statEntEl = document.getElementById("statEntCount");
        const statConcEl = document.getElementById("statConcCount");
        const statClmEl = document.getElementById("statClmCount");

        if (sectionsEl) sectionsEl.innerHTML = '<li class="inspector-loading-state"><i class="fa-solid fa-spinner fa-spin"></i> Loading sections &amp; outline...</li>';
        if (entitiesEl) entitiesEl.innerHTML = '<div class="inspector-loading-state"><i class="fa-solid fa-spinner fa-spin"></i> Loading entity chips...</div>';
        if (conceptsEl) conceptsEl.innerHTML = '<div class="inspector-loading-state"><i class="fa-solid fa-spinner fa-spin"></i> Loading legal concepts...</div>';
        if (claimsEl) claimsEl.innerHTML = '<li class="inspector-loading-state"><i class="fa-solid fa-spinner fa-spin"></i> Loading verified claims...</li>';

        try {
            const res = await authFetch(`/api/documents/${encodeURIComponent(documentId)}`);
            if (seq !== inspectorLoadSequence) return;

            if (!res.ok) {
                const errMsg = `Failed to load document knowledge (HTTP ${res.status})`;
                if (sectionsEl) sectionsEl.innerHTML = `<li class="inspector-empty-state"><i class="fa-solid fa-triangle-exclamation"></i><span>${errMsg}</span></li>`;
                if (entitiesEl) entitiesEl.innerHTML = `<div class="inspector-empty-state"><i class="fa-solid fa-triangle-exclamation"></i><span>${errMsg}</span></div>`;
                if (conceptsEl) conceptsEl.innerHTML = `<div class="inspector-empty-state"><i class="fa-solid fa-triangle-exclamation"></i><span>${errMsg}</span></div>`;
                if (claimsEl) claimsEl.innerHTML = `<li class="inspector-empty-state"><i class="fa-solid fa-triangle-exclamation"></i><span>${errMsg}</span></li>`;
                return;
            }

            const data = await res.json();
            const doc = data.document || {};
            const k = data.knowledge || {};
            const sections = k.sections || [];
            const paragraphs = k.paragraphs || [];
            const entities = k.entities || [];
            const concepts = k.concepts || [];
            const claims = k.claims || [];

            const activeDocTitle = document.getElementById("activeDocTitle");
            const activeDocTypeBadge = document.getElementById("activeDocTypeBadge");
            const activeDocStatusBadge = document.getElementById("activeDocStatusBadge");
            const activeDocIcon = document.getElementById("activeDocIcon");

            if (activeDocTitle) activeDocTitle.textContent = doc.filename || "Active Document";
            if (activeDocTypeBadge) activeDocTypeBadge.textContent = (doc.document_type || "Document").replace(/_/g, " ");
            if (activeDocStatusBadge) activeDocStatusBadge.textContent = (doc.status || "COMPLETED").toUpperCase();
            if (activeDocIcon) {
                const ext = (doc.filename || "").split(".").pop().toUpperCase();
                const iconMap = { PDF: "fa-file-pdf", DOCX: "fa-file-word", TXT: "fa-file-lines", PNG: "fa-file-image", JPG: "fa-file-image", JPEG: "fa-file-image" };
                activeDocIcon.className = `fa-solid ${iconMap[ext] || "fa-file-lines"}`;
            }

            if (countSecEl) countSecEl.textContent = sections.length;
            if (countEntEl) countEntEl.textContent = entities.length;
            if (countConcEl) countConcEl.textContent = concepts.length;
            if (countClmEl) countClmEl.textContent = claims.length;

            if (statSecEl) statSecEl.textContent = sections.length;
            if (statEntEl) statEntEl.textContent = entities.length;
            if (statConcEl) statConcEl.textContent = concepts.length;
            if (statClmEl) statClmEl.textContent = claims.length;

            // 1. Sections
            if (sectionsEl) {
                if (sections.length > 0) {
                    sectionsEl.innerHTML = sections.map((s, idx) => {
                        const secParas = paragraphs.filter(p => p.section_id === s.section_id);
                        const previewText = secParas.map(p => p.text).join(" ").trim();
                        const clauseCount = secParas.filter(p => p.is_clause).length;

                        return `
                        <li class="section-item">
                            <div class="section-head">
                                <span class="section-title">
                                    <i class="fa-regular fa-file-lines"></i>
                                    ${escapeHtml(s.title || `Section ${idx + 1}`)}
                                </span>
                                <div class="section-badges">
                                    <span class="badge-level">Lvl ${s.level || 1}</span>
                                    <span class="badge-page">P.${s.page_number || 1}</span>
                                    ${clauseCount > 0 ? `<span class="badge-level" style="background: rgba(16, 185, 129, 0.15); border-color: rgba(16, 185, 129, 0.3); color: #6ee7b7;"><i class="fa-solid fa-gavel"></i> ${clauseCount} clause${clauseCount > 1 ? 's' : ''}</span>` : ''}
                                </div>
                            </div>
                            ${previewText ? `
                                <div class="section-preview" title="Section excerpt">
                                    ${escapeHtml(previewText.slice(0, 240))}${previewText.length > 240 ? '...' : ''}
                                </div>
                            ` : ''}
                        </li>`;
                    }).join("");
                } else {
                    sectionsEl.innerHTML = '<li class="inspector-empty-state"><i class="fa-solid fa-folder-open"></i><span>No structured sections detected in this document.</span></li>';
                }
            }

            // 2. Entities
            currentEntitiesCache = entities;
            activeEntityFilter = "all";
            renderEntityFilters(entities);
            renderEntityChips(entities, "all");

            // 3. Concepts
            if (conceptsEl) {
                if (concepts.length > 0) {
                    conceptsEl.innerHTML = concepts.map(c => {
                        const topic = (c.topic || "Legal Concept").toLowerCase();
                        const icon = CONCEPT_ICONS[topic] || "fa-scale-balanced";
                        const matchPct = Math.round((Number(c.relevance_score) || 0.8) * 100);

                        return `
                        <div class="concept-card">
                            <div class="concept-card-top">
                                <span class="concept-title">
                                    <i class="fa-solid ${icon}"></i>
                                    ${escapeHtml(c.topic || "Concept")}
                                </span>
                                <span class="concept-score">${matchPct}% Relevance</span>
                            </div>
                            <p class="concept-desc">${escapeHtml(c.description || "Provisions relating to this topic identified in document.")}</p>
                        </div>`;
                    }).join("");
                } else {
                    conceptsEl.innerHTML = '<div class="inspector-empty-state"><i class="fa-solid fa-scale-unbalanced"></i><span>No legal concepts identified for this document.</span></div>';
                }
            }

            // 4. Claims
            if (claimsEl) {
                if (claims.length > 0) {
                    claimsEl.innerHTML = claims.map(cl => {
                        const ctype = (cl.claim_type || "obligation").toLowerCase();
                        const confPct = Math.round((Number(cl.confidence) || 0.9) * 100);

                        return `
                        <li class="claim-card">
                            <div class="claim-card-top">
                                <div class="claim-badge-group">
                                    <i class="fa-solid fa-circle-check claim-check"></i>
                                    <span class="claim-type-pill claim-type-${ctype}">${escapeHtml(ctype)}</span>
                                </div>
                                <span class="claim-conf-badge"><i class="fa-solid fa-shield-halved"></i> ${confPct}% Conf</span>
                            </div>
                            <p class="claim-text">${escapeHtml(cl.claim_text || "")}</p>
                        </li>`;
                    }).join("");
                } else {
                    claimsEl.innerHTML = '<li class="inspector-empty-state"><i class="fa-solid fa-quote-left"></i><span>No verified claims extracted for this document.</span></li>';
                }
            }

        } catch (err) {
            if (seq !== inspectorLoadSequence) return;
            console.error("Inspector loading error:", err);
            const errNotice = escapeHtml(err.message);
            if (sectionsEl) sectionsEl.innerHTML = `<li class="inspector-empty-state"><i class="fa-solid fa-triangle-exclamation"></i><span>Error: ${errNotice}</span></li>`;
            if (entitiesEl) entitiesEl.innerHTML = `<div class="inspector-empty-state"><i class="fa-solid fa-triangle-exclamation"></i><span>Error: ${errNotice}</span></div>`;
            if (conceptsEl) conceptsEl.innerHTML = `<div class="inspector-empty-state"><i class="fa-solid fa-triangle-exclamation"></i><span>Error: ${errNotice}</span></div>`;
            if (claimsEl) claimsEl.innerHTML = `<li class="inspector-empty-state"><i class="fa-solid fa-triangle-exclamation"></i><span>Error: ${errNotice}</span></li>`;
        }
    }
});
