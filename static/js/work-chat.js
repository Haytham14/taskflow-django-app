(function () {
  const root = document.querySelector(".work-chat-page");
  if (!root) return;

  const apiBase = root.dataset.apiBase || "/api/chat/";
  const currentUserId = Number(root.dataset.currentUserId || 0);
  const currentIsAdmin = root.dataset.currentIsAdmin === "true";
  const usersScript = document.getElementById("work-chat-users-data");
  const availableUsers = usersScript ? JSON.parse(usersScript.textContent || "[]") : [];

  const conversationList = document.getElementById("work-chat-conversation-list");
  const conversationSearch = document.getElementById("work-chat-conversation-search");
  const channelTitle = document.getElementById("work-chat-channel-title");
  const channelMeta = document.getElementById("work-chat-channel-meta");
  const channelAvatar = document.getElementById("work-chat-channel-avatar");
  const thread = document.getElementById("work-chat-thread");
  const messageSearchToggle = document.getElementById("work-chat-message-search-toggle");
  const messageSearch = document.getElementById("work-chat-message-search");
  const messageSearchInput = document.getElementById("work-chat-message-search-input");
  const messageSearchClose = document.getElementById("work-chat-message-search-close");
  const composer = document.getElementById("work-chat-composer");
  const input = document.getElementById("work-chat-input");
  const sendButton = document.getElementById("work-chat-send");
  const attachButton = document.getElementById("work-chat-attach-btn");
  const fileInput = document.getElementById("work-chat-file-input");
  const fileChip = document.getElementById("work-chat-file-chip");
  const fileName = document.getElementById("work-chat-file-name");
  const fileClear = document.getElementById("work-chat-file-clear");
  const newButton = document.getElementById("work-chat-new-discussion");
  const newModal = document.getElementById("work-chat-new-modal");
  const newForm = document.getElementById("work-chat-new-form");
  const newClose = document.getElementById("work-chat-new-close");
  const newCancel = document.getElementById("work-chat-new-cancel");
  const memberOptions = document.getElementById("work-chat-member-options");
  const directOptions = document.getElementById("work-chat-direct-options");
  const modeButtons = newForm.querySelectorAll("[data-mode]");
  const channelOnlyFields = newForm.querySelectorAll(".work-chat-channel-only");
  const directOnlyFields = newForm.querySelectorAll(".work-chat-direct-only");
  const newNameInput = newForm.elements.name;
  const backdrop = document.getElementById("work-chat-modal-backdrop");
  const optionsToggle = document.getElementById("work-chat-options-toggle");
  const optionsMenu = document.getElementById("work-chat-options-menu");
  const editAction = optionsMenu.querySelector("[data-action='edit']");
  const deleteAction = optionsMenu.querySelector("[data-action='delete']");
  const membersModal = document.getElementById("work-chat-members-modal");
  const membersClose = document.getElementById("work-chat-members-close");
  const membersList = document.getElementById("work-chat-members-list");
  const editModal = document.getElementById("work-chat-edit-modal");
  const editForm = document.getElementById("work-chat-edit-form");
  const editDelete = document.getElementById("work-chat-edit-delete");
  const editName = document.getElementById("work-chat-edit-name");
  const editDescription = document.getElementById("work-chat-edit-description");
  const editMembers = document.getElementById("work-chat-edit-members");
  const editClose = document.getElementById("work-chat-edit-close");
  const editCancel = document.getElementById("work-chat-edit-cancel");

  let channels = [];
  let activeChannel = null;
  let activeMessages = [];
  let pendingFile = null;
  let creationMode = "channel";
  let liveTimer = null;
  let liveSyncRunning = false;
  let audioContext = null;
  const lastChannelStorageKey = `work-chat:last-channel:${currentUserId}`;

  function rememberedChannelId() {
    try {
      const channelId = Number(window.localStorage.getItem(lastChannelStorageKey));
      return Number.isInteger(channelId) && channelId > 0 ? channelId : null;
    } catch (_error) {
      return null;
    }
  }

  function rememberChannel(channelId) {
    try {
      window.localStorage.setItem(lastChannelStorageKey, String(channelId));
    } catch (_error) {
      // Chat still works when browser storage is disabled.
    }
  }

  function csrfToken() {
    const inputToken = document.querySelector("[name=csrfmiddlewaretoken]");
    if (inputToken) return inputToken.value;
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function initials(name) {
    const parts = String(name || "?").trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return "?";
    return parts.slice(0, 2).map((part) => part[0]).join("").toUpperCase();
  }

  function avatarClass(value) {
    const text = String(value || "");
    const total = Array.from(text).reduce((sum, char) => sum + char.charCodeAt(0), 0);
    return ["work-avatar-mg", "work-avatar-am", "work-avatar-hh"][total % 3];
  }

  function channelName(channel) {
    return channel ? (channel.display_name || channel.name || "Conversation") : "";
  }

  function formatTime(isoValue) {
    if (!isoValue) return "";
    const date = new Date(isoValue);
    const now = new Date();
    if (date.toDateString() === now.toDateString()) {
      return date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
    }
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    if (date.toDateString() === yesterday.toDateString()) return "Hier";
    return date.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" });
  }

  function formatMessageTime(isoValue) {
    if (!isoValue) return "";
    const date = new Date(isoValue);
    const now = new Date();
    const time = date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
    if (date.toDateString() === now.toDateString()) return time;
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    if (date.toDateString() === yesterday.toDateString()) return `Hier, ${time}`;
    return `${date.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" })}, ${time}`;
  }

  function presenceLabel(user) {
    return user && user.is_online ? "En ligne" : "Hors ligne";
  }

  function fileSize(bytes) {
    let size = Number(bytes || 0);
    const units = ["o", "Ko", "Mo", "Go"];
    for (const unit of units) {
      if (size < 1024 || unit === units[units.length - 1]) {
        return unit === "o" ? `${Math.round(size)} ${unit}` : `${size.toFixed(1)} ${unit}`;
      }
      size /= 1024;
    }
    return "";
  }

  function enableAudio() {
    if (!audioContext) {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext) audioContext = new AudioContext();
    }
    if (audioContext && audioContext.state === "suspended") audioContext.resume().catch(() => {});
  }

  function playMessageSound(kind) {
    enableAudio();
    if (!audioContext || audioContext.state !== "running") return;
    const oscillator = audioContext.createOscillator();
    const gain = audioContext.createGain();
    const now = audioContext.currentTime;
    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(kind === "received" ? 660 : 520, now);
    oscillator.frequency.exponentialRampToValueAtTime(kind === "received" ? 880 : 700, now + 0.1);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.12, now + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.16);
    oscillator.connect(gain);
    gain.connect(audioContext.destination);
    oscillator.start(now);
    oscillator.stop(now + 0.17);
  }

  function refreshGlobalUnreadBadge() {
    window.dispatchEvent(new CustomEvent("taskflow:chat-unread-changed"));
  }

  async function request(path, options = {}) {
    const headers = options.headers ? { ...options.headers } : {};
    if (!(options.body instanceof FormData)) {
      headers["Content-Type"] = headers["Content-Type"] || "application/json";
    }
    if ((options.method || "GET") !== "GET") {
      headers["X-CSRFToken"] = csrfToken();
    }

    const response = await fetch(`${apiBase}${path}`, {
      credentials: "same-origin",
      ...options,
      headers,
    });
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json") ? await response.json() : {};
    if (!response.ok) throw new Error(payload.error || "Action impossible pour le moment.");
    return payload;
  }

  function applyPresence(users) {
    const statuses = new Map(users.map((user) => [Number(user.id), user]));
    availableUsers.forEach((user) => {
      const status = statuses.get(Number(user.id));
      if (status) Object.assign(user, status);
    });
    channels.forEach((channel) => {
      if (channel.direct_user) {
        const status = statuses.get(Number(channel.direct_user.id));
        if (status) Object.assign(channel.direct_user, status);
      }
    });
    if (activeChannel && activeChannel.direct_user) {
      const status = statuses.get(Number(activeChannel.direct_user.id));
      if (status) Object.assign(activeChannel.direct_user, status);
    }
    if (activeChannel && activeChannel.members) {
      activeChannel.members.forEach((member) => {
        const status = statuses.get(Number(member.user.id));
        if (status) Object.assign(member.user, status);
      });
    }
    renderConversations();
    renderHeader(activeChannel);
  }

  async function refreshPresence() {
    const users = await request("presence/");
    applyPresence(users);
  }

  function messageSignature(messages) {
    return messages.map((message) => [
      message.id,
      message.updated_at,
      message.is_deleted,
      (message.reactions || []).map((reaction) => `${reaction.emoji}:${reaction.count}`).join(","),
      (message.read_by || []).map((reader) => `${reader.id}:${reader.read_at}`).join(","),
    ].join(":")).join("|");
  }

  async function syncLive() {
    if (liveSyncRunning || document.hidden) return;
    liveSyncRunning = true;
    try {
      const channelId = activeChannel && activeChannel.id;
      const previousLastMessages = new Map(
        channels.map((channel) => [channel.id, channel.last_message && channel.last_message.id])
      );
      const requests = [request("channels/"), request("presence/")];
      if (channelId) requests.push(request(`channels/${channelId}/messages/?per_page=80`));
      const [latestChannels, users, messagePayload] = await Promise.all(requests);

      const receivedNewMessage = channels.length && latestChannels.some((channel) => {
        const latest = channel.last_message;
        return latest
          && previousLastMessages.has(channel.id)
          && previousLastMessages.get(channel.id) !== latest.id
          && latest.sender_id !== currentUserId;
      });
      channels = latestChannels;
      applyPresence(users);
      if (receivedNewMessage) {
        playMessageSound("received");
        refreshGlobalUnreadBadge();
      }

      if (!channelId) return;
      const listedChannel = channels.find((channel) => channel.id === channelId);
      if (!listedChannel) {
        activeChannel = null;
        activeMessages = [];
        renderHeader(null);
        renderMessages();
        return;
      }

      if (activeChannel.direct_user && listedChannel.direct_user) {
        activeChannel.direct_user = listedChannel.direct_user;
      }
      activeChannel.members_count = listedChannel.members_count;
      activeChannel.is_archived = listedChannel.is_archived;
      renderHeader(activeChannel);

      const latestMessages = messagePayload.results || [];
      if (messageSignature(latestMessages) !== messageSignature(activeMessages)) {
        const stayAtBottom = thread.scrollHeight - thread.scrollTop - thread.clientHeight < 90;
        activeMessages = latestMessages;
        renderMessages(stayAtBottom);
        await request(`channels/${channelId}/mark-read/`, { method: "POST", body: "{}" });
        const current = channels.find((channel) => channel.id === channelId);
        if (current) current.unread_count = 0;
        renderConversations();
        refreshGlobalUnreadBadge();
      }
    } catch (_error) {
      // A later poll retries automatically after temporary network failures.
    } finally {
      liveSyncRunning = false;
    }
  }

  function startLiveUpdates() {
    syncLive();
    liveTimer = window.setInterval(syncLive, 2500);
  }

  function setComposerEnabled(enabled) {
    input.disabled = !enabled;
    sendButton.disabled = !enabled;
    attachButton.disabled = !enabled;
  }

  function stateMessage(text) {
    return `<p class="work-chat-state">${escapeHtml(text)}</p>`;
  }

  function renderConversations() {
    const query = conversationSearch ? conversationSearch.value.trim().toLowerCase() : "";
    const filtered = channels.filter((channel) => channelName(channel).toLowerCase().includes(query));

    if (!filtered.length) {
      conversationList.innerHTML = stateMessage(query ? "Aucune conversation trouvée." : "Aucune conversation.");
      return;
    }

    const renderConversationButton = (channel) => {
      const last = channel.last_message;
      const active = activeChannel && activeChannel.id === channel.id;
      const name = channelName(channel);
      const senderLabel = last && last.sender_id === currentUserId
        ? "Vous"
        : (last && last.sender ? last.sender.split(" ")[0] : "");
      const preview = last ? `${senderLabel}: ${last.content}` : "Aucun message pour le moment.";
      const isDirect = channel.channel_type === "direct";
      const avatar = isDirect
        ? `<span class="work-chat-conversation-avatar gray">${escapeHtml(initials(name))}<i class="work-chat-presence-dot ${channel.direct_user && channel.direct_user.is_online ? "online" : "offline"}"></i></span>`
        : `<span class="work-chat-conversation-avatar channel">#</span>`;
      const unread = channel.unread_count ? `<em>${escapeHtml(channel.unread_count)}</em>` : "";
      return `
        <button type="button" class="work-chat-conversation ${isDirect ? "is-direct" : "is-channel"} ${active ? "active" : ""}" data-channel-id="${channel.id}">
          ${avatar}
          <span class="work-chat-conversation-body">
            <strong>${escapeHtml(name)}</strong>
            <small>${escapeHtml(preview)}</small>
          </span>
          <span class="work-chat-conversation-meta">
            <time>${escapeHtml(formatTime(last && last.created_at))}</time>
            ${unread}
          </span>
        </button>
      `;
    };
    const channelItems = filtered.filter((channel) => channel.channel_type !== "direct");
    const directItems = filtered.filter((channel) => channel.channel_type === "direct");
    const renderGroup = (label, items, canAdd = false) => items.length ? `
      <div class="work-chat-conversation-group">
        <div class="work-chat-conversation-group-head">
          <p class="work-chat-conversation-group-title">${label}</p>
          ${canAdd ? '<button type="button" data-new-discussion aria-label="Nouvelle discussion">+</button>' : ""}
        </div>
        ${items.map(renderConversationButton).join("")}
      </div>
    ` : "";

    conversationList.innerHTML = [
      renderGroup("Canaux", channelItems, true),
      renderGroup("Messages directs", directItems),
    ].join("");
  }

  function renderHeader(channel) {
    if (!channel) {
      channelTitle.textContent = "Sélectionnez une conversation";
      channelMeta.textContent = "Aucun canal actif";
      channelAvatar.textContent = "";
      channelAvatar.hidden = true;
      channelAvatar.closest(".work-chat-title-block").classList.add("no-avatar");
      if (editAction) editAction.hidden = true;
      if (deleteAction) deleteAction.hidden = true;
      setComposerEnabled(false);
      return;
    }
    const name = channelName(channel);
    const isDirect = channel.channel_type === "direct";
    channelTitle.textContent = isDirect ? name : `# ${name}`;
    if (isDirect) {
      const online = channel.direct_user && channel.direct_user.is_online;
      channelMeta.innerHTML = `<span class="work-chat-meta-presence ${online ? "online" : "offline"}"></span>${presenceLabel(channel.direct_user)}`;
    } else {
      const memberCount = channel.members_count || 0;
      const onlineCount = (channel.members || []).filter((member) => member.user.is_online).length;
      channelMeta.innerHTML = `${memberCount} membre${memberCount > 1 ? "s" : ""} - ${onlineCount} en ligne`;
    }
    channelAvatar.textContent = channel.channel_type === "direct" ? initials(name) : "";
    channelAvatar.hidden = channel.channel_type !== "direct";
    channelAvatar.closest(".work-chat-title-block").classList.toggle("no-avatar", channel.channel_type !== "direct");
    if (editAction) editAction.hidden = !currentIsAdmin || channel.channel_type === "direct";
    if (deleteAction) deleteAction.hidden = !currentIsAdmin || channel.channel_type === "direct";
    setComposerEnabled(!channel.is_archived);
  }

  function renderMessages(scrollToBottom = true) {
    if (!activeChannel) {
      thread.innerHTML = `<p class="work-chat-empty">Choisissez une conversation pour afficher les messages.</p>`;
      return;
    }
    const searchQuery = messageSearchInput.value.trim().toLowerCase();
    const visibleMessages = searchQuery
      ? activeMessages.filter((message) => {
          const attachmentNames = (message.attachments || []).map((item) => item.original_name).join(" ");
          return `${message.content} ${message.sender && message.sender.name} ${attachmentNames}`.toLowerCase().includes(searchQuery);
        })
      : activeMessages;
    if (!visibleMessages.length) {
      thread.innerHTML = `<p class="work-chat-empty">${searchQuery ? "Aucun message correspondant." : "Aucun message dans cette discussion."}</p>`;
      return;
    }

    thread.innerHTML = visibleMessages.map((message) => {
      const sender = message.sender || {};
      const isSent = Number(sender.id) === currentUserId;
      const readers = (message.read_by || []).filter((reader) => Number(reader.id) !== currentUserId);
      let receipt = "";
      if (isSent) {
        if (activeChannel.channel_type === "direct") {
          receipt = `<div class="work-chat-receipt">${readers.length ? "Vu" : "Envoyé"}</div>`;
        } else if (readers.length) {
          const avatars = readers.slice(0, 4).map((reader) => `
            <span class="work-chat-receipt-avatar ${avatarClass(reader.initials || reader.name)}" title="${escapeHtml(reader.name)}">
              ${escapeHtml(reader.initials || initials(reader.name))}
            </span>
          `).join("");
          receipt = `
            <div class="work-chat-receipt work-chat-receipt-channel">
              <span class="work-chat-receipt-avatars">${avatars}</span>
            </div>
          `;
        } else {
          receipt = '<div class="work-chat-receipt">Envoyé</div>';
        }
      }
      const attachments = (message.attachments || []).map((attachment) => `
        <a href="${escapeHtml(attachment.url)}" class="work-chat-attachment" target="_blank" rel="noopener">
          <span class="work-chat-file-icon" aria-hidden="true">${escapeHtml(attachment.file_type || "FILE")}</span>
          <span>
            <strong>${escapeHtml(attachment.original_name)}</strong>
            <small>${escapeHtml(attachment.file_type || "Fichier")} &middot; ${escapeHtml(fileSize(attachment.file_size))}</small>
          </span>
        </a>
      `).join("");
      return `
        <article class="work-chat-message ${isSent ? "is-sent" : "is-received"}" data-message-id="${message.id}">
          ${isSent ? "" : `<span class="work-avatar ${avatarClass(sender.initials || sender.name)}">${escapeHtml(sender.initials || initials(sender.name))}</span>`}
          <div class="work-chat-message-body">
            <div class="work-chat-message-bubble">
              <header>
                <strong>${escapeHtml(isSent ? "Vous" : (sender.name || "Utilisateur"))}</strong>
                <span>${escapeHtml(formatMessageTime(message.created_at))}</span>
              </header>
              <p>${escapeHtml(message.content).replace(/\n/g, "<br>")}</p>
              ${attachments}
            </div>
            ${receipt}
          </div>
        </article>
      `;
    }).join("");
    if (scrollToBottom) thread.scrollTop = thread.scrollHeight;
  }

  async function loadChannels(selectChannelId) {
    conversationList.innerHTML = stateMessage("Chargement des conversations...");
    channels = await request("channels/");
    if (!channels.length) {
      activeChannel = null;
      activeMessages = [];
      renderHeader(null);
      renderConversations();
      renderMessages();
      return;
    }

    const selected = channels.find((channel) => channel.id === selectChannelId)
      || (activeChannel && channels.find((channel) => channel.id === activeChannel.id))
      || channels[0];
    await selectChannel(selected.id);
  }

  async function selectChannel(channelId) {
    const channel = await request(`channels/${channelId}/`);
    activeChannel = channel;
    rememberChannel(channel.id);
    renderHeader(channel);
    renderConversations();

    const payload = await request(`channels/${channelId}/messages/?per_page=80`);
    activeMessages = payload.results || [];
    renderMessages();
    await request(`channels/${channelId}/mark-read/`, { method: "POST", body: "{}" });
    const listChannel = channels.find((item) => item.id === channelId);
    if (listChannel) listChannel.unread_count = 0;
    renderConversations();
    refreshGlobalUnreadBadge();
  }

  async function sendMessage(event) {
    event.preventDefault();
    if (!activeChannel) return;

    const content = input.value.trim();
    if (!content && !pendingFile) return;

    const data = new FormData();
    data.append("content", content);
    if (pendingFile) data.append("attachments", pendingFile);

    sendButton.disabled = true;
    try {
      const message = await request(`channels/${activeChannel.id}/messages/`, { method: "POST", body: data });
      activeMessages.push(message);
      playMessageSound("sent");
      input.value = "";
      clearFile();
      renderMessages();
      await loadChannels(activeChannel.id);
    } catch (error) {
      alert(error.message);
    } finally {
      sendButton.disabled = false;
    }
  }

  function clearFile() {
    pendingFile = null;
    fileInput.value = "";
    fileChip.hidden = true;
    fileName.textContent = "";
  }

  function openModal(modal) {
    backdrop.hidden = false;
    modal.hidden = false;
  }

  function closeModals() {
    backdrop.hidden = true;
    newModal.hidden = true;
    membersModal.hidden = true;
    editModal.hidden = true;
  }

  function setCreationMode(mode) {
    creationMode = mode;
    modeButtons.forEach((button) => button.classList.toggle("active", button.dataset.mode === mode));
    channelOnlyFields.forEach((element) => { element.hidden = mode === "direct"; });
    directOnlyFields.forEach((element) => { element.hidden = mode !== "direct"; });
    newNameInput.required = mode !== "direct";
    newForm.elements.channel_type.value = mode === "direct" ? "direct" : "team";
  }

  function renderMemberOptions() {
    if (!availableUsers.length) {
      memberOptions.innerHTML = stateMessage("Aucun autre utilisateur disponible.");
      directOptions.innerHTML = stateMessage("Aucun autre utilisateur disponible.");
      return;
    }
    memberOptions.innerHTML = availableUsers.map((user) => `
      <label>
        <input type="checkbox" name="member_ids" value="${user.id}">
        <span>${escapeHtml(user.name)} <small><i class="work-chat-inline-presence ${user.is_online ? "online" : "offline"}"></i>${escapeHtml(presenceLabel(user))}</small></span>
      </label>
    `).join("");
    directOptions.innerHTML = availableUsers.map((user) => `
      <label>
        <input type="radio" name="direct_user_id" value="${user.id}">
        <span>${escapeHtml(user.name)} <small><i class="work-chat-inline-presence ${user.is_online ? "online" : "offline"}"></i>${escapeHtml(presenceLabel(user))}</small></span>
      </label>
    `).join("");
  }

  function openNewDiscussion() {
    renderMemberOptions();
    setCreationMode("channel");
    openModal(newModal);
    newNameInput.focus();
  }

  async function createDiscussion(event) {
    event.preventDefault();
    const data = new FormData(newForm);
    try {
      let channel;
      if (creationMode === "direct") {
        const userId = data.get("direct_user_id");
        if (!userId) throw new Error("Choisissez un utilisateur.");
        channel = await request("direct-conversations/", {
          method: "POST",
          body: JSON.stringify({ user_id: userId }),
        });
      } else {
        channel = await request("channels/", { method: "POST", body: data });
      }
      newForm.reset();
      closeModals();
      await loadChannels(channel.id);
    } catch (error) {
      alert(error.message);
    }
  }

  async function showMembers() {
    if (!activeChannel) return;
    const members = await request(`channels/${activeChannel.id}/members/`);
    membersList.innerHTML = members.map((member) => `
      <article class="work-chat-member-row">
        <span class="work-avatar ${avatarClass(member.user.initials)}">${escapeHtml(member.user.initials)}</span>
        <span>
          <strong>${escapeHtml(member.user.name)}</strong>
          <small><i class="work-chat-inline-presence ${member.user.is_online ? "online" : "offline"}"></i>${escapeHtml(presenceLabel(member.user))} · ${escapeHtml(member.role)}</small>
        </span>
      </article>
    `).join("") || stateMessage("Aucun membre.");
    openModal(membersModal);
  }

  function renderEditMembers(members) {
    const memberIds = new Set(members.map((member) => member.user.id));
    const addableUsers = availableUsers.filter((user) => !memberIds.has(user.id));
    const currentRows = members.map((member) => {
      const canRemove = member.user.id !== currentUserId && member.role !== "owner";
      return `
        <article class="work-chat-edit-member-row">
          <span>
            <strong>${escapeHtml(member.user.name)}</strong>
            <small>${escapeHtml(member.role)}</small>
          </span>
          ${canRemove ? `<button type="button" data-remove-member="${member.user.id}">Retirer</button>` : `<em>Fixe</em>`}
        </article>
      `;
    }).join("");
    const addRows = addableUsers.length ? `
      <div class="work-chat-edit-add-members">
        <p>Ajouter des membres</p>
        ${addableUsers.map((user) => `
          <label>
            <input type="checkbox" name="add_member_ids" value="${user.id}">
            <span>${escapeHtml(user.name)} <small><i class="work-chat-inline-presence ${user.is_online ? "online" : "offline"}"></i>${escapeHtml(presenceLabel(user))}</small></span>
          </label>
        `).join("")}
      </div>
    ` : `<p class="work-chat-state">Tous les utilisateurs sont deja dans ce canal.</p>`;
    editMembers.innerHTML = `${currentRows}${addRows}`;
  }

  async function openEditChannel() {
    if (!activeChannel) return;
    if (activeChannel.channel_type === "direct") {
      alert("Une conversation directe ne se modifie pas comme un canal.");
      return;
    }
    if (!currentIsAdmin) {
      alert("Seuls les administrateurs peuvent modifier les canaux.");
      return;
    }
    const channel = await request(`channels/${activeChannel.id}/`);
    activeChannel = channel;
    editName.value = channel.name;
    editDescription.value = channel.description || "";
    renderEditMembers(channel.members || []);
    openModal(editModal);
  }

  async function saveEditChannel(event) {
    event.preventDefault();
    if (!activeChannel) return;
    const addMemberIds = Array.from(editForm.querySelectorAll("[name='add_member_ids']:checked")).map((input) => input.value);
    try {
      await request(`channels/${activeChannel.id}/`, {
        method: "PUT",
        body: JSON.stringify({
          name: editName.value.trim(),
          description: editDescription.value.trim(),
        }),
      });
      if (addMemberIds.length) {
        await request(`channels/${activeChannel.id}/members/`, {
          method: "POST",
          body: JSON.stringify({ user_ids: addMemberIds, role: "member" }),
        });
      }
      closeModals();
      await loadChannels(activeChannel.id);
    } catch (error) {
      alert(error.message);
    }
  }

  async function removeMember(userId) {
    if (!activeChannel) return;
    await request(`channels/${activeChannel.id}/members/${userId}/`, { method: "DELETE", body: "{}" });
    const channel = await request(`channels/${activeChannel.id}/`);
    activeChannel = channel;
    renderEditMembers(channel.members || []);
    renderHeader(channel);
  }

  async function deleteActiveChannel() {
    if (!activeChannel) return;
    if (!currentIsAdmin) {
      alert("Seuls les administrateurs peuvent supprimer les canaux.");
      return;
    }
    if (!confirm(`Supprimer "${channelName(activeChannel)}" ?`)) return;
    await request(`channels/${activeChannel.id}/`, { method: "DELETE", body: "{}" });
    closeModals();
    activeChannel = null;
    activeMessages = [];
    await loadChannels();
  }

  async function handleOptions(event) {
    const action = event.target.dataset.action;
    if (!action || !activeChannel) return;
    optionsMenu.hidden = true;

    if (action === "refresh") await selectChannel(activeChannel.id);
    if (action === "mark-read") {
      await request(`channels/${activeChannel.id}/mark-read/`, { method: "POST", body: "{}" });
      const channel = channels.find((item) => item.id === activeChannel.id);
      if (channel) channel.unread_count = 0;
      renderConversations();
      refreshGlobalUnreadBadge();
    }
    if (action === "members") await showMembers();
    if (action === "edit") await openEditChannel();
    if (action === "delete") await deleteActiveChannel();
  }

  conversationList.addEventListener("click", (event) => {
    if (event.target.closest("[data-new-discussion]")) {
      openNewDiscussion();
      return;
    }
    const button = event.target.closest("[data-channel-id]");
    if (!button) return;
    selectChannel(Number(button.dataset.channelId)).catch((error) => alert(error.message));
  });

  if (conversationSearch) conversationSearch.addEventListener("input", renderConversations);
  messageSearchInput.addEventListener("input", renderMessages);
  messageSearchToggle.addEventListener("click", () => {
    messageSearch.hidden = !messageSearch.hidden;
    if (!messageSearch.hidden) messageSearchInput.focus();
  });
  messageSearchClose.addEventListener("click", () => {
    messageSearchInput.value = "";
    messageSearch.hidden = true;
    renderMessages();
  });
  composer.addEventListener("submit", sendMessage);

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      composer.requestSubmit();
    }
  });

  attachButton.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => {
    pendingFile = fileInput.files[0] || null;
    fileChip.hidden = !pendingFile;
    fileName.textContent = pendingFile ? pendingFile.name : "";
  });
  fileClear.addEventListener("click", clearFile);

  newButton.addEventListener("click", openNewDiscussion);
  modeButtons.forEach((button) => {
    button.addEventListener("click", () => setCreationMode(button.dataset.mode));
  });
  newForm.addEventListener("submit", createDiscussion);
  newClose.addEventListener("click", closeModals);
  newCancel.addEventListener("click", closeModals);
  backdrop.addEventListener("click", closeModals);
  membersClose.addEventListener("click", closeModals);
  editClose.addEventListener("click", closeModals);
  editCancel.addEventListener("click", closeModals);
  editDelete.addEventListener("click", () => {
    deleteActiveChannel().catch((error) => alert(error.message));
  });
  editForm.addEventListener("submit", saveEditChannel);
  editMembers.addEventListener("click", (event) => {
    const button = event.target.closest("[data-remove-member]");
    if (!button) return;
    removeMember(Number(button.dataset.removeMember)).catch((error) => alert(error.message));
  });

  optionsToggle.addEventListener("click", () => {
    optionsMenu.hidden = !optionsMenu.hidden;
  });
  optionsMenu.addEventListener("click", (event) => {
    handleOptions(event).catch((error) => alert(error.message));
  });

  document.addEventListener("keydown", (event) => {
    enableAudio();
    if (event.key === "Escape") {
      optionsMenu.hidden = true;
      closeModals();
    }
  });
  document.addEventListener("pointerdown", enableAudio, { once: true });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) syncLive();
  });
  window.addEventListener("pagehide", () => window.clearInterval(liveTimer));

  startLiveUpdates();
  loadChannels(rememberedChannelId()).catch((error) => {
    conversationList.innerHTML = stateMessage(error.message);
    thread.innerHTML = `<p class="work-chat-empty">${escapeHtml(error.message)}</p>`;
  });
})();
