import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import './email-assistant.css';
import {
  GraduationCap, MessageCircle, Plus, Search, Send, LogOut, Sparkles,
  UserRound, PanelLeftClose, PanelLeftOpen, ArrowUpRight, Trash2, X,
  Mail, RefreshCw, Check, Save, ShieldCheck, Inbox,
} from 'lucide-react';

import {
  auth,
  chats,
  clearToken,
  downloadDocument,
  saveToken,
  token,
  emailAssistant,
} from './api';

const dateLabel = (v) =>
  new Date(v).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });

const asArray = (v) => (Array.isArray(v) ? v : []);

// Matches [Source 1], [Source 1, page 3] and the 【 】 variants.

// Supports:
// [Source 1]
// [Source 1, page 3]
// 【Source 1】
// (See Sources 1, 3, 4)
// (Sources 1, 3, 4)

const pattern =
  /\((?:See\s+)?Sources?\s+(\d+(?:\s*,\s*\d+)*)(?:,\s*page\s+([^)]+))?\)|[\[【]Source\s+(\d+)(?:,\s*page\s+([^\]】]+))?[\]】]/gi;

function CitationText({ content, sources, onDownload, downloading }) {
  const text = content ?? '';

  const sourceMap = new Map(
    asArray(sources).map((source, index) => [
      String(source.source_id ?? index + 1),
      source,
    ])
  );

  const parts = [];
  let last = 0;
  let match;
  let key = 0;

  pattern.lastIndex = 0;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) {
      parts.push(text.slice(last, match.index));
    }

    const numbers = match[1]
      ? match[1].split(',').map((n) => n.trim())
      : [match[3]];

    const isPlural = Boolean(match[1]);
    const page = match[2] || match[4];

    if (isPlural) parts.push('(See ');

    numbers.forEach((number, index) => {
      if (index > 0) parts.push(', ');

      const source = sourceMap.get(number);

      if (source?.document_id) {
        const isDownloading =
          String(downloading) === String(source.document_id);

        parts.push(
          <button
            key={`citation-${key++}`}
            type="button"
            className="citation"
            disabled={isDownloading}
            onClick={() => onDownload(source)}
            title={`Download ${source.document_title || 'source document'}`}
          >
            {isDownloading ? 'Downloading...' : `Source ${number}`}
          </button>
        );
      } else {
        parts.push(`Source ${number}`);
      }
    });

    if (page) parts.push(`, page ${page}`);

    if (isPlural) parts.push(')');

    last = pattern.lastIndex;
  }

  if (last < text.length) {
    parts.push(text.slice(last));
  }

  return <>{parts}</>;
}


function AuthScreen({ onLogin }) {
  const [step, setStep] = useState('email');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function continueWithEmail(e) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const result = await auth.checkEmail(email.trim());
      setStep(result.registered ? 'login' : 'register');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function submitAccount(e) {
    e.preventDefault();
    setError('');
    if (step === 'register' && password !== confirm) {
      setError('The passwords do not match.');
      return;
    }
    setBusy(true);
    try {
      if (step === 'register') await auth.register(name.trim(), email.trim(), password);
      const result = await auth.login(email.trim(), password);
      saveToken(result.access_token);
      onLogin(await auth.me());
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function back() {
    setStep('email');
    setPassword('');
    setConfirm('');
    setError('');
  }

  const title =
    step === 'email' ? 'Welcome to the Academy'
      : step === 'login' ? 'Welcome back'
        : 'Create your account';

  const subtitle =
    step === 'email' ? 'Enter your email address to get started.'
      : step === 'login' ? 'This email already has an account. Enter your password to continue.'
        : 'Your email is not registered yet. Create an account to start chatting.';

  return (
    <main className="auth">
      <section className="brand-side">
        <div className="logo">
          <span className="mark"><GraduationCap /></span>Academy <i>Concierge</i>
        </div>
        <div className="brand-copy">
          <small>YOUR ACADEMY, ONE CONVERSATION AWAY</small>
          <h1>Guidance that<br /><em>moves you forward.</em></h1>
          <p>Ask questions, explore programs, and get support throughout your Academy journey.</p>
          <div className="tagline"><Sparkles size={16} /> Your personal Academy assistant</div>
        </div>
        <footer>ACADEMY CONCIERGE · STUDENT SUPPORT</footer>
      </section>

      <section className="auth-side">
        <div className="auth-card">
          <div className="mobile-logo">
            <span className="mark"><GraduationCap /></span> Academy Concierge
          </div>
          <small className="eyebrow">
            {step === 'email' ? 'WELCOME' : 'CONTINUE TO YOUR ACCOUNT'}
          </small>
          <h2>{title}</h2>
          <p>{subtitle}</p>

          {step === 'email' ? (
            <form onSubmit={continueWithEmail}>
              <label>
                Email address
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  autoComplete="email"
                />
              </label>
              {error && <div className="error">{error}</div>}
              <button className="primary" disabled={busy}>
                {busy ? 'Checking…' : 'Continue'} <ArrowUpRight size={17} />
              </button>
            </form>
          ) : (
            <form onSubmit={submitAccount}>
              {step === 'register' && (
                <label>
                  Full name
                  <input
                    required
                    minLength="2"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Your full name"
                    autoComplete="name"
                  />
                </label>
              )}
              <label>
                Email address
                <input type="email" value={email} readOnly />
              </label>
              <label>
                {step === 'register' ? 'Create password' : 'Password'}
                <input
                  type="password"
                  minLength="8"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={step === 'register' ? 'At least 8 characters' : 'Enter your password'}
                  autoComplete={step === 'register' ? 'new-password' : 'current-password'}
                />
              </label>
              {step === 'register' && (
                <label>
                  Confirm password
                  <input
                    type="password"
                    minLength="8"
                    required
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    placeholder="Re-enter your password"
                    autoComplete="new-password"
                  />
                </label>
              )}
              {error && <div className="error">{error}</div>}
              <button className="primary" disabled={busy}>
                {busy ? 'Please wait…' : step === 'login' ? 'Sign in' : 'Create account'}{' '}
                <ArrowUpRight size={17} />
              </button>
              <button type="button" className="back-link" onClick={back}>
                Use a different email
              </button>
            </form>
          )}

          <div className="secure">
            ● Your password is securely hashed and never visible to Academy staff.
          </div>
        </div>
      </section>
    </main>
  );
}

const SUGGESTIONS_BY_ROLE = {
  guest: [
    {
      title: 'Explore our courses',
      question: 'What courses does the Academy offer?',
      description: 'Discover our courses, programs and admission requirements.',
      icon: GraduationCap,
    },
    {
      title: 'Successful graduates',
      question: 'Show me the successful graduates of the Academy.',
      description: 'Discover our graduates and their achievements.',
      icon: Sparkles,
    },
  ],
};

function EmailAssistantView({ initialNotice = '' }) {
  const [connection, setConnection] = useState(null);
  const [emails, setEmails] = useState([]);
  const [selected, setSelected] = useState(null);
  const [replyDraft, setReplyDraft] = useState('');
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState(initialNotice);

  const selectedEmail = emails.find(
    (email) => email.id === selected
  ) || null;

  const refresh = useCallback(async () => {
    setError('');

    try {
      const [connectionResult, messageResult] = await Promise.all([
        emailAssistant.connection(),
        emailAssistant.messages(filter === 'all' ? null : filter),
      ]);

      const messageList = Array.isArray(messageResult) ? messageResult : [];
      setConnection(connectionResult);
      setEmails(messageList);

      setSelected((current) => {
        if (current && messageList.some((email) => email.id === current)) {
          return current;
        }

        return messageList[0]?.id ?? null;
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    setReplyDraft(selectedEmail?.reply_draft || '');
  }, [selectedEmail?.id, selectedEmail?.reply_draft]);

  async function connectGmail() {
    setError('');
    setActionBusy(true);

    try {
      const result = await emailAssistant.connect();

      if (!result.authorization_url) {
        throw new Error('Google authorization URL was not returned.');
      }

      window.location.assign(result.authorization_url);
    } catch (err) {
      setError(err.message);
      setActionBusy(false);
    }
  }

  async function syncEmails() {
    setError('');
    setNotice('');
    setSyncing(true);

    try {
      const result = await emailAssistant.sync();

      await refresh();

      setNotice(
        result?.message || 'Inbox synchronization completed.'
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setSyncing(false);
    }
  }

  async function generateDraft() {
    if (!selectedEmail) return;

    setError('');
    setActionBusy(true);

    try {
      const result = await emailAssistant.generateDraft(selectedEmail.id);

      setReplyDraft(result.reply_draft || '');

      await refresh();

      setNotice('AI reply draft generated.');
    } catch (err) {
      setError(err.message);
    } finally {
      setActionBusy(false);
    }
  }

  async function saveDraft() {
    if (!selectedEmail || !replyDraft.trim()) return;

    setError('');
    setActionBusy(true);

    try {
      await emailAssistant.updateDraft(
        selectedEmail.id,
        replyDraft.trim()
      );

      await refresh();

      setNotice('Draft saved successfully.');
    } catch (err) {
      setError(err.message);
    } finally {
      setActionBusy(false);
    }
  }

  async function approveDraft() {
    if (!selectedEmail) return;

    setError('');
    setActionBusy(true);

    try {
      await emailAssistant.approve(selectedEmail.id);

      await refresh();

      setNotice('Reply approved.');
    } catch (err) {
      setError(err.message);
    } finally {
      setActionBusy(false);
    }
  }

  async function sendReply() {
    if (!selectedEmail) return;

    if (
      !window.confirm(
        `Send this reply to ${selectedEmail.sender}?`
      )
    ) {
      return;
    }

    setError('');
    setActionBusy(true);

    try {
      await emailAssistant.send(selectedEmail.id);

      await refresh();

      setNotice('Reply sent successfully.');
    } catch (err) {
      setError(err.message);
    } finally {
      setActionBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="email-loading">
        <RefreshCw className="spin" size={22} />
        Loading Email Assistant...
      </div>
    );
  }

  return (
    <div className="email-workspace">
      <div className="email-heading">
        <div>
          <span className="eyebrow">ADMIN WORKSPACE</span>
          <h1>Email Assistant</h1>
          <p>
            Manage Academy emails and prepare AI-assisted replies.
          </p>
        </div>

        {connection?.connected && (
          <button
            type="button"
            className="email-secondary-btn"
            onClick={syncEmails}
            disabled={syncing}
          >
            <RefreshCw size={16} className={syncing ? 'spin' : ''} />
            {syncing ? 'Syncing...' : 'Sync inbox'}
          </button>
        )}
      </div>

      {error && (
        <div className="email-alert error">
          {error}
        </div>
      )}

      {notice && (
        <div className="email-alert success">
          {notice}
        </div>
      )}

      {!connection?.connected ? (
        <div className="email-connect-card">
          <div className="email-connect-icon">
            <Mail size={28} />
          </div>

          <h2>Connect your Academy Gmail account</h2>

          <p>
            Connect Gmail to synchronize incoming messages, generate
            AI-assisted replies, and send approved responses.
          </p>

          <button
            type="button"
            className="email-primary-btn"
            onClick={connectGmail}
            disabled={actionBusy}
          >
            <Mail size={17} />
            {actionBusy ? 'Connecting...' : 'Connect Gmail'}
          </button>

          <small>
            Gmail access is restricted to administrators.
          </small>
        </div>
      ) : (
        <>
          <div className="email-connection">
            <div className="email-connection-icon">
              <Check size={17} />
            </div>

            <div>
              <strong>Gmail connected</strong>
              <small>{connection.email}</small>
            </div>

            <span className="email-connected-label">Connected</span>
          </div>

          <div className="email-filters">
            {[
              ['all', 'All emails'],
              ['received', 'Received'],
              ['drafted', 'Drafts'],
              ['approved', 'Approved'],
              ['sent', 'Sent'],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={filter === value ? 'active' : ''}
                onClick={() => setFilter(value)}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="email-layout">
            <section className="email-list">
              <div className="email-list-heading">
                <strong>
                  <Inbox size={16} />
                  Inbox
                </strong>
                <span>{emails.length}</span>
              </div>

              {emails.length === 0 ? (
                <div className="email-empty">
                  <Mail size={25} />
                  <p>No emails found.</p>
                  <small>Try synchronizing your inbox.</small>
                </div>
              ) : (
                emails.map((email) => (
                  <button
                    type="button"
                    key={email.id}
                    className={`email-item ${
                      selected === email.id ? 'selected' : ''
                    }`}
                    onClick={() => setSelected(email.id)}
                  >
                    <div className="email-item-top">
                      <strong>{email.sender || 'Unknown sender'}</strong>
                      <span className={`email-status ${email.status}`}>
                        {email.status}
                      </span>
                    </div>

                    <b>{email.subject || '(No subject)'}</b>

                    <p>
                      {(email.body || '').slice(0, 100)}
                    </p>
                  </button>
                ))
              )}
            </section>

            <section className="email-detail">
              {!selectedEmail ? (
                <div className="email-empty">
                  <Mail size={30} />
                  <p>Select an email to view its details.</p>
                </div>
              ) : (
                <>
                  <div className="email-detail-heading">
                    <div>
                      <span className="eyebrow">EMAIL DETAILS</span>
                      <h2>
                        {selectedEmail.subject || '(No subject)'}
                      </h2>
                    </div>
                    <span className={`email-status ${selectedEmail.status}`}>
                      {selectedEmail.status}
                    </span>
                  </div>

                  <div className="email-metadata">
                    <p>
                      <strong>From:</strong> {selectedEmail.sender}
                    </p>
                    <p>
                      <strong>To:</strong> {selectedEmail.recipient}
                    </p>
                    <p>
                      <strong>Date:</strong>{' '}
                      {selectedEmail.received_at
                        ? new Date(selectedEmail.received_at).toLocaleString()
                        : 'Unknown'}
                    </p>
                  </div>

                  <div className="email-original">
                    <h3>Original message</h3>
                    <div>{selectedEmail.body || 'No message body.'}</div>
                  </div>

                  <div className="email-reply">
                    <div className="email-reply-heading">
                      <h3>
                        <Sparkles size={17} />
                        AI-assisted reply
                      </h3>

                      <button
                        type="button"
                        className="email-secondary-btn"
                        onClick={generateDraft}
                        disabled={
                          actionBusy || selectedEmail.status === 'sent'
                        }
                      >
                        <Sparkles size={15} />
                        Generate draft
                      </button>
                    </div>

                    <textarea
                      value={replyDraft}
                      onChange={(e) => setReplyDraft(e.target.value)}
                      placeholder="Generate or write a reply..."
                      disabled={selectedEmail.status === 'sent'}
                    />

                    <div className="email-actions">
                      <button
                        type="button"
                        className="email-secondary-btn"
                        onClick={saveDraft}
                        disabled={
                          actionBusy ||
                          !replyDraft.trim() ||
                          selectedEmail.status === 'sent'
                        }
                      >
                        <Save size={15} />
                        Save draft
                      </button>

                      <button
                        type="button"
                        className="email-secondary-btn"
                        onClick={approveDraft}
                        disabled={
                          actionBusy ||
                          !replyDraft.trim() ||
                          selectedEmail.status === 'sent' ||
                          selectedEmail.status === 'approved'
                        }
                      >
                        <ShieldCheck size={15} />
                        Approve
                      </button>

                      <button
                        type="button"
                        className="email-primary-btn"
                        onClick={sendReply}
                        disabled={
                          actionBusy ||
                          selectedEmail.status !== 'approved'
                        }
                      >
                        <Send size={15} />
                        Send reply
                      </button>
                    </div>

                    <small className="email-safety-note">
                      Replies must be reviewed and approved before sending.
                    </small>
                  </div>
                </>
              )}
            </section>
          </div>
        </>
      )}
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);
  const [items, setItems] = useState([]);
  const [active, setActive] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(null);
  const [error, setError] = useState('');
  const [collapsed, setCollapsed] = useState(false);
  const [search, setSearch] = useState('');
  const [view, setView] = useState('chat');
  const [gmailNotice, setGmailNotice] = useState('');

  // This version currently provides the public guest welcome suggestions.
  const suggestions = SUGGESTIONS_BY_ROLE[user?.role] || SUGGESTIONS_BY_ROLE.guest;

  const end = useRef(null);
  const input = useRef(null);
  const openRequest = useRef(0); // guards against stale responses in open()

  // Restore session
  useEffect(() => {
    (async () => {
      if (token()) {
        try {
          setUser(await auth.me());
        } catch {
          clearToken();
        }
      }
      setChecking(false);
    })();
  }, []);

  // Handle the redirect back from Google's Gmail authorization flow.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const gmailStatus = params.get('gmail');

    if (gmailStatus === 'connected') {
      setGmailNotice('Gmail connected successfully!');
      setView('email');
    } else if (gmailStatus === 'error') {
      setGmailNotice('Gmail connection failed or was cancelled. Please try again.');
      setView('email');
    }

    if (gmailStatus) {
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, []);

  const open = useCallback(async (id) => {
    const req = ++openRequest.current;
    setActive(id);
    setLoading(true);
    setError('');
    try {
      const list = await chats.messages(id);
      if (req === openRequest.current) setMessages(asArray(list));
    } catch (e) {
      if (req === openRequest.current) setError(e.message);
    } finally {
      if (req === openRequest.current) setLoading(false);
    }
  }, []);

  // Initial load after login: fetch the list and open the most recent chat
  useEffect(() => {
    if (!user) return;
    (async () => {
      try {
        const list = asArray(await chats.list());
        setItems(list);
        if (list[0]) await open(list[0].id);
      } catch (e) {
        setError(e.message);
      }
    })();
  }, [user, open]);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, busy]);

  // Auto-grow the textarea
  useEffect(() => {
    const el = input.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [draft]);

  function newChat() {
    openRequest.current++; // ignore any in-flight open()
    setLoading(false);
    setActive(null);
    setMessages([]);
    setDraft('');
    setError('');
    input.current?.focus();
  }

  async function send(e) {
    e?.preventDefault();
    const q = draft.trim();
    if (!q || busy) return;

    setDraft('');
    setBusy(true);
    setError('');

    const userMsg = {
      id: crypto.randomUUID(),
      sender: 'user',
      content: q,
      created_at: new Date().toISOString(),
    };
    setMessages((m) => [...m, userMsg]);

    try {
      let id = active;
      if (!id) {
        const c = await chats.create();
        id = c.id;
        openRequest.current++; // a new chat has nothing to load
        setActive(id);
        setItems((x) => [c, ...x]);
      }

      const result = await chats.send(id, q);
      setMessages((m) => [
        ...m,
        {
          id: crypto.randomUUID(),
          sender: 'assistant',
          content: result.answer,
          sources: asArray(result.sources),
          created_at: new Date().toISOString(),
          handoff_required: result.handoff_required,
        },
      ]);
    } catch (err) {
      setMessages((m) => m.filter((x) => x.id !== userMsg.id));
      setDraft(q);
      setError(err.message);
      setBusy(false);
      return;
    }

    // Refresh only the sidebar (titles, order). Do not reload the thread.
    try {
      setItems(asArray(await chats.list()));
    } catch {
      /* the sidebar can stay stale, the message already went through */
    }
    setBusy(false);
  }

  async function downloadCitation(source) {
    setError('');
    setDownloading(source.document_id);
    try {
      await downloadDocument(source.document_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setDownloading(null);
    }
  }

  async function removeConversation(id) {
    const conversation = items.find((x) => x.id === id);
    const label = conversation?.title || 'New conversation';
    if (!window.confirm(`Delete “${label}”? This cannot be undone.`)) return;

    setError('');
    try {
      await chats.remove(id);
      const remaining = items.filter((x) => x.id !== id);
      setItems(remaining);
      if (active === id) {
        if (remaining[0]) await open(remaining[0].id);
        else newChat();
      }
    } catch (err) {
      setError(err.message);
    }
  }

  function logout() {
    clearToken();
    openRequest.current++;
    setUser(null);
    setItems([]);
    setMessages([]);
    setActive(null);
  }

  function onComposerKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send(e);
    }
  }

  const filtered = useMemo(() => {
    const term = search.toLowerCase();
    return items.filter((x) =>
      `${x.title || 'new conversation'} ${dateLabel(x.created_at)}`
        .toLowerCase()
        .includes(term)
    );
  }, [items, search]);

  if (checking) return <div className="loading-screen">Loading your workspace…</div>;
  if (!user) return <AuthScreen onLogin={setUser} />;

  return (
    <div className={`shell ${collapsed ? 'collapsed' : ''}`}>
      <aside className="sidebar">
        <div className="side-top">
          <div className="logo">
            <span className="mark"><GraduationCap /></span>
            {!collapsed && <>Academy <i>Concierge</i></>}
          </div>
          <button
            type="button"
            className="icon-btn"
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            onClick={() => setCollapsed(!collapsed)}
          >
            {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
          </button>
        </div>

        <button type="button" className="new-chat" onClick={newChat}>
          <Plus size={18} />
          {!collapsed && 'New conversation'}
        </button>

        {user.role === 'admin' && (
          <button
            type="button"
            className={`email-nav-btn ${view === 'email' ? 'active' : ''}`}
            onClick={() => {
              setView('email');
              setError('');
            }}
            title="Email Assistant"
          >
            <Mail size={18} />
            {!collapsed && 'Email Assistant'}
          </button>
        )}

        {!collapsed && (
          <>
            <div className="history-title">YOUR HISTORY</div>
            <div className="search">
              <Search size={15} />
              <input
                placeholder="Search conversations"
                aria-label="Search conversations"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div className="history">
              {filtered.length ? (
                filtered.map((c) => (
                  <div
                    key={c.id}
                    className={`history-item ${active === c.id ? 'selected' : ''}`}
                    role="button"
                    tabIndex="0"
                    onClick={() => open(c.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') open(c.id);
                    }}
                  >
                    <MessageCircle size={16} />
                    <span>
                      <b>{c.title || 'New conversation'}</b>
                      <small>{dateLabel(c.created_at)}</small>
                    </span>
                    <button
                      className="delete-chat"
                      type="button"
                      title="Delete conversation"
                      aria-label={`Delete ${c.title || 'conversation'}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        removeConversation(c.id);
                      }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))
              ) : (
                <p className="empty">
                  {search ? 'No matching conversations' : 'Your conversations will appear here.'}
                </p>
              )}
            </div>
          </>
        )}

        <div className="account">
          {!collapsed && (
            <div className="account-info">
              <b>{user.full_name}</b>
              <small>{user.email}</small>
            </div>
          )}
          <button
            type="button"
            className="icon-btn logout"
            title="Sign out"
            aria-label="Sign out"
            onClick={logout}
          >
            <LogOut size={17} />
          </button>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <span className="online" /> Academy Assistant <span className="slash">/</span>
            <span className="muted">Student support</span>
          </div>
          <div className="top-user">
            {user.full_name}
            <span className="avatar small">{(user.full_name || 'U').slice(0, 1).toUpperCase()}</span>
          </div>
        </header>

        {view === 'email' && user.role === 'admin' ? (
          <section className="stage email-stage">
            <EmailAssistantView initialNotice={gmailNotice} />
          </section>
        ) : (
          <section className="stage">
          {messages.length === 0 && !loading ? (
            <div className="welcome">
              <div className="welcome-icon"><Sparkles /></div>
              <small className="eyebrow">ACADEMY CONCIERGE</small>
              <h1>How can we help<br /><em>you today?</em></h1>
              <p>
                Ask about programs, admissions, schedules, payments, or anything else
                related to your Academy experience.
              </p>
              <div className="suggestions">
                {suggestions.map((s) => {
                  const Icon = s.icon;

                  return (
                    <button
                      key={s.title}
                      type="button"
                      onClick={() => {
                        setDraft(s.question);
                        input.current?.focus();
                      }}
                    >
                      <span className="suggestion-copy">
                        <span className="suggestion-heading">
                          <Icon size={18} />
                          <strong>{s.title}</strong>
                        </span>
                        <small>{s.description}</small>
                      </span>
                      <ArrowUpRight size={16} />
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="messages">
              {loading ? (
                <p className="loading-inline">Loading conversation…</p>
              ) : (
                messages.map((m, i) => (
                  <div
                    key={m.id ?? i}
                    className={`message ${m.sender === 'user' ? 'mine' : ''}`}
                  >
                    {m.sender !== 'user' && (
                      <div className="bot-avatar"><Sparkles size={16} /></div>
                    )}
                    <div className="message-body">
                      <div className="meta">
                        {m.sender === 'user' ? 'You' : 'Academy Assistant'}{' '}
                        <time>
                          {m.created_at
                            ? new Date(m.created_at).toLocaleTimeString([], {
                                hour: '2-digit',
                                minute: '2-digit',
                              })
                            : ''}
                        </time>
                      </div>
                      <div className="bubble">
                        {m.sender === 'assistant' ? (
                          <CitationText
                            content={m.content}
                            sources={m.sources}
                            onDownload={downloadCitation}
                            downloading={downloading}
                          />
                        ) : (
                          m.content
                        )}
                      </div>
                      {m.handoff_required && (
                        <small className="handoff">
                          Your request has been flagged for human assistance.
                        </small>
                      )}
                    </div>
                    {m.sender === 'user' && (
                      <div className="avatar user-avatar"><UserRound size={16} /></div>
                    )}
                  </div>
                ))
              )}
              {busy && (
                <div className="message">
                  <div className="bot-avatar"><Sparkles size={16} /></div>
                  <div className="bubble typing">•••</div>
                </div>
              )}
              <div ref={end} />
            </div>
          )}
          </section>
        )}

        {view === 'chat' && error && (
          <div className="error chat-error">
            {error}
            <button type="button" aria-label="Dismiss error" onClick={() => setError('')}>
              <X size={15} />
            </button>
          </div>
        )}

        {view === 'chat' && (
        <div className="composer-wrap">
          <form className="composer" onSubmit={send}>
            <textarea
              ref={input}
              rows="1"
              aria-label="Message"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onComposerKeyDown}
              placeholder="Message your Academy assistant…"
            />
            <button type="submit" aria-label="Send message" disabled={!draft.trim() || busy}>
              <Send size={17} />
            </button>
          </form>
          <div className="disclaimer">
            Academy Concierge can make mistakes. Please verify important information.
          </div>
        </div>
        )}
      </main>
    </div>
  );
}