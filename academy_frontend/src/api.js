
const BASE = (
  import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
).replace(/\/$/, '');

// ─────────────────────────────────────────────
// AUTH TOKEN
// ─────────────────────────────────────────────

export const token = () => localStorage.getItem('concierge_token');

export const saveToken = (value) => {
  localStorage.setItem('concierge_token', value);
};

export const clearToken = () => {
  localStorage.removeItem('concierge_token');
};

// ─────────────────────────────────────────────
// BASE API REQUEST
// ─────────────────────────────────────────────

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
  } catch {
    throw new Error(
      'Cannot connect to the Academy server. Check that the backend is running.'
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

// ─────────────────────────────────────────────
// DOCUMENT DOWNLOAD
// ─────────────────────────────────────────────

export async function downloadDocument(url, filename) {
  const headers = {};
  const accessToken = token();

  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  const response = await fetch(`${BASE}${url}`, { headers });

  if (!response.ok) {
    throw new Error('Failed to download document.');
  }

  const blob = await response.blob();
  const objectUrl = window.URL.createObjectURL(blob);

  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = filename || 'document';

  document.body.appendChild(link);
  link.click();
  link.remove();

  window.URL.revokeObjectURL(objectUrl);
}

// ─────────────────────────────────────────────
// AUTHENTICATION
// ─────────────────────────────────────────────

export const auth = {
  login: (email, password) =>
    api('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  register: (payload) =>
    api('/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  me: () => api('/auth/me'),
};

// ─────────────────────────────────────────────
// CHAT
// ─────────────────────────────────────────────

export const chats = {
  list: () => api('/chats'),

  get: (id) => api(`/chats/${id}`),

  create: (payload = {}) =>
    api('/chats', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  send: (chatId, message) =>
    api(`/chats/${chatId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),

  delete: (id) =>
    api(`/chats/${id}`, {
      method: 'DELETE',
    }),
};

// ─────────────────────────────────────────────
// GMAIL EMAIL ASSISTANT (ADMIN)
// ─────────────────────────────────────────────

export const emailAssistant = {
  // Check Gmail connection status
  connection: () =>
    api('/email-assistant/connection'),

  // Start Google OAuth connection
  connect: () =>
    api('/email-assistant/connect', {
      method: 'POST',
    }),

  // Sync Gmail inbox
  sync: () =>
    api('/email-assistant/sync', {
      method: 'POST',
    }),

  // Get email messages, optionally filtered by status
  messages: (status) => {
    const query = status
      ? `?status_filter=${encodeURIComponent(status)}`
      : '';

    return api(`/email-assistant/messages${query}`);
  },

  // Generate an AI reply draft using Academy knowledge
  generateDraft: (emailId) =>
    api(`/email-assistant/${emailId}/draft`, {
      method: 'POST',
    }),

  // Update/edit the generated reply draft
  updateDraft: (emailId, replyDraft) =>
    api(`/email-assistant/${emailId}/draft`, {
      method: 'PUT',
      body: JSON.stringify({
        reply_draft: replyDraft,
      }),
    }),

  // Approve the reply
  approve: (emailId) =>
    api(`/email-assistant/${emailId}/approve`, {
      method: 'POST',
    }),

  // Send the approved reply through Gmail
  send: (emailId) =>
    api(`/email-assistant/${emailId}/send`, {
      method: 'POST',
    }),
};
