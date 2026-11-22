
const BASE = (
  import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
).replace(/\/$/, '');

// ─────────────────────────────────────
// TOKEN MANAGEMENT
// ─────────────────────────────────────

export const token = () => localStorage.getItem('concierge_token');

export const saveToken = (value) => {
  localStorage.setItem('concierge_token', value);
};

export const clearToken = () => {
  localStorage.removeItem('concierge_token');
};

// ─────────────────────────────────────
// BASE API REQUEST
// ─────────────────────────────────────

export async function api(path, options = {}) {
  const headers = {
    ...(options.body ? { 'Content-Type': 'application/json' } : {}),
    ...(options.headers || {}),
  };

  const accessToken = token();

  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  let response;

  try {
    response = await fetch(`${BASE}${path}`, {
      ...options,
      headers,
    });
  } catch (error) {
    console.error('API connection error:', error);

    throw new Error(
      'Cannot connect to the Academy server. Please check your connection.'
    );
  }

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const detail = data?.detail;

    throw new Error(
      typeof detail === 'string'
        ? detail
        : `Request failed (${response.status})`
    );
  }

  return data;
}

// ─────────────────────────────────────
// DOCUMENT DOWNLOAD
// ─────────────────────────────────────

export async function downloadDocument(documentId) {
  const headers = {};
  const accessToken = token();

  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  const response = await fetch(
    `${BASE}/documents/${documentId}/download`,
    { headers }
  );

  if (!response.ok) {
    throw new Error('Failed to download document.');
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);

  const link = document.createElement('a');
  link.href = url;
  link.download = `document-${documentId}`;

  document.body.appendChild(link);
  link.click();
  link.remove();

  URL.revokeObjectURL(url);
}

// ─────────────────────────────────────
// AUTHENTICATION
// ─────────────────────────────────────

export const auth = {
  checkEmail: (email) =>
    api('/users/check-email', {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),

  login: (email, password) =>
    api('/users/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  register: (full_name, email, password) =>
    api('/users/register', {
      method: 'POST',
      body: JSON.stringify({
        full_name,
        email,
        password,
      }),
    }),

  me: () => api('/users/me'),
};

// ─────────────────────────────────────
// CHAT
// ─────────────────────────────────────

export const chats = {
  list: () => api('/conversations/'),

  create: () =>
    api('/conversations/', {
      method: 'POST',
      body: JSON.stringify({
        channel: 'website',
        language: navigator.language?.slice(0, 2) || 'en',
      }),
    }),

  messages: (id) =>
    api(`/conversations/${id}/messages`),

  send: (conversation_id, question) =>
    api('/ai/chat', {
      method: 'POST',
      body: JSON.stringify({
        conversation_id,
        question,
      }),
    }),

  remove: (id) =>
    api(`/conversations/${id}`, {
      method: 'DELETE',
    }),
};

// ─────────────────────────────────────
// GMAIL EMAIL ASSISTANT
// ─────────────────────────────────────


export const emailAssistant = {
  // Check Gmail connection
  connection: () =>
    api('/email-assistant/connection'),

  // Start Google OAuth authorization
  connect: () =>
    api('/email-assistant/connect'),

  // Synchronize Gmail inbox
  sync: () =>
    api('/email-assistant/sync', {
      method: 'POST',
    }),

  // Retrieve emails
  messages: (status) => {
    const query = status
      ? `?status_filter=${encodeURIComponent(status)}`
      : '';

    return api(`/email-assistant/messages${query}`);
  },

  // Generate AI reply
  generateDraft: (id) =>
    api(`/email-assistant/messages/${id}/draft`, {
      method: 'POST',
    }),

  // Update reply draft
  updateDraft: (id, reply_draft) =>
    api(`/email-assistant/messages/${id}/draft`, {
      method: 'PUT',
      body: JSON.stringify({ reply_draft }),
    }),

  // Approve reply
  approve: (id) =>
    api(`/email-assistant/messages/${id}/approve`, {
      method: 'POST',
    }),

  // Send approved reply
  send: (id) =>
    api(`/email-assistant/messages/${id}/send`, {
      method: 'POST',
    }),
};

