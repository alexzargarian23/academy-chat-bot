import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  GraduationCap, MessageCircle, Plus, Search, Send, LogOut, Sparkles, PanelLeftClose,
  PanelLeftOpen, Trash2, X, Menu, ArrowDown, RotateCw, FileText, CalendarDays, CreditCard,
} from 'lucide-react';
import { auth, chats, clearToken, downloadDocument, token } from './api';
import AuthScreen from './components/AuthScreen';
import Message from './components/Message';
import {
  asArray, dateLabel, groupByDate, readFlag, writeFlag, useMediaQuery,
} from './utils';

const SUGGESTIONS = [
  { icon: GraduationCap, text: 'What programs does the Academy offer?' },
  { icon: FileText, text: 'How can I apply?' },
  { icon: CalendarDays, text: 'I need help with my schedule' },
  { icon: CreditCard, text: 'How do payments work?' },
];

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
  const [failed, setFailed] = useState(false);
  const [collapsed, setCollapsed] = useState(() => readFlag('sidebar-collapsed'));
  const [drawer, setDrawer] = useState(false);
  const [confirmId, setConfirmId] = useState(null);
  const [showJump, setShowJump] = useState(false);
  const [search, setSearch] = useState('');

  const mobile = useMediaQuery('(max-width: 800px)');
  const rail = collapsed && !mobile;

  const stage = useRef(null);
  const end = useRef(null);
  const input = useRef(null);
  const stick = useRef(true); // keep pinned to the newest message
  const lastQuestion = useRef('');
  const openRequest = useRef(0); // guards against stale responses in open()

  // Restore session
  useEffect(() => {
    (async () => {
      if (token()) {
        try { setUser(await auth.me()); } catch { clearToken(); }
      }
      setChecking(false);
    })();
  }, []);

  const open = useCallback(async (id) => {
    const req = ++openRequest.current;
    stick.current = true;
    setActive(id);
    setLoading(true);
    setError('');
    setFailed(false);
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

  // Auto-scroll only while the reader is near the bottom
  useEffect(() => {
    if (stick.current) end.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, busy, loading]);

  function onStageScroll() {
    const el = stage.current;
    if (!el) return;
    const gap = el.scrollHeight - el.scrollTop - el.clientHeight;
    stick.current = gap < 120;
    setShowJump(gap > 300);
  }

  function jumpToLatest() {
    stick.current = true;
    end.current?.scrollIntoView({ behavior: 'smooth' });
  }

  // Auto-grow the textarea
  useEffect(() => {
    const el = input.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [draft]);

  // Close the drawer with Escape
  useEffect(() => {
    if (!drawer) return undefined;
    const onKey = (e) => e.key === 'Escape' && setDrawer(false);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [drawer]);

  function toggleCollapsed() {
    setCollapsed((c) => {
      writeFlag('sidebar-collapsed', !c);
      return !c;
    });
  }

  function newChat() {
    openRequest.current++; // ignore any in-flight open()
    setLoading(false);
    setActive(null);
    setMessages([]);
    setDraft('');
    setError('');
    setFailed(false);
    setDrawer(false);
    input.current?.focus();
  }

  async function ask(text) {
    const q = text.trim();
    if (!q || busy) return;

    lastQuestion.current = q;
    stick.current = true;
    setDraft('');
    setBusy(true);
    setError('');
    setFailed(false);

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
      setFailed(true);
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

  function send(e) {
    e?.preventDefault();
    ask(draft);
  }

  async function downloadCitation(source) {
    setError('');
    setFailed(false);
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
    setConfirmId(null);
    setError('');
    setFailed(false);
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
    setDrawer(false);
  }

  function onComposerKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send(e);
    }
  }

  const groups = useMemo(() => {
    const term = search.trim().toLowerCase();
    const filtered = items.filter((x) =>
      `${x.title || 'new conversation'} ${dateLabel(x.created_at)}`.toLowerCase().includes(term)
    );
    return groupByDate(filtered);
  }, [items, search]);

  if (checking) return <div className="loading-screen">Loading your workspace…</div>;
  if (!user) return <AuthScreen onLogin={setUser} />;

  const initial = (user.full_name || user.email).slice(0, 1).toUpperCase();
  const activeTitle = items.find((x) => x.id === active)?.title;
  const empty = messages.length === 0 && !loading;

  return (
    <div className={`shell ${rail ? 'collapsed' : ''} ${drawer ? 'drawer-open' : ''}`}>
      {drawer && <div className="backdrop" onClick={() => setDrawer(false)} aria-hidden="true" />}

      <aside className="sidebar" aria-label="Conversations">
        <div className="side-top">
          <div className="logo">
            <span className="mark"><GraduationCap /></span>
            {!rail && <>Academy <i>Concierge</i></>}
          </div>
          {mobile ? (
            <button type="button" className="icon-btn" aria-label="Close menu" onClick={() => setDrawer(false)}>
              <X />
            </button>
          ) : (
            <button
              type="button"
              className="icon-btn"
              aria-label={rail ? 'Expand sidebar' : 'Collapse sidebar'}
              onClick={toggleCollapsed}
            >
              {rail ? <PanelLeftOpen /> : <PanelLeftClose />}
            </button>
          )}
        </div>

        <button type="button" className="new-chat" onClick={newChat} aria-label="New conversation">
          <Plus size={18} />
          {!rail && 'New conversation'}
        </button>

        {!rail && (
          <>
            <div className="search">
              <Search size={15} />
              <input
                placeholder="Search conversations"
                aria-label="Search conversations"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>

            <nav className="history">
              {groups.length ? (
                groups.map(([label, list]) => (
                  <section key={label}>
                    <h3 className="history-group">{label}</h3>
                    {list.map((c) => (
                      <div key={c.id} className={`history-item ${active === c.id ? 'selected' : ''}`}>
                        {confirmId === c.id ? (
                          <div className="confirm-row" role="group" aria-label="Confirm delete">
                            <span>Delete this chat?</span>
                            <button type="button" className="danger-btn" onClick={() => removeConversation(c.id)}>
                              Delete
                            </button>
                            <button type="button" className="ghost-btn" onClick={() => setConfirmId(null)}>
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <>
                            <button
                              type="button"
                              className="history-open"
                              aria-current={active === c.id ? 'true' : undefined}
                              onClick={() => { open(c.id); setDrawer(false); }}
                            >
                              <MessageCircle size={16} />
                              <span>
                                <b>{c.title || 'New conversation'}</b>
                                <small>{dateLabel(c.created_at)}</small>
                              </span>
                            </button>
                            <button
                              className="delete-chat"
                              type="button"
                              title="Delete conversation"
                              aria-label={`Delete ${c.title || 'conversation'}`}
                              onClick={() => setConfirmId(c.id)}
                            >
                              <Trash2 size={15} />
                            </button>
                          </>
                        )}
                      </div>
                    ))}
                  </section>
                ))
              ) : (
                <p className="empty">
                  {search ? 'No conversations match your search.' : 'Your conversations will appear here.'}
                </p>
              )}
            </nav>
          </>
        )}

        <div className="account">
          <div className="avatar">{initial}</div>
          {!rail && (
            <div className="account-info">
              <b>{user.full_name}</b>
              <small>{user.email}</small>
            </div>
          )}
          <button type="button" className="icon-btn logout" title="Sign out" aria-label="Sign out" onClick={logout}>
            <LogOut size={17} />
          </button>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="topbar-left">
            <button type="button" className="icon-btn menu-btn" aria-label="Open menu" onClick={() => setDrawer(true)}>
              <Menu />
            </button>
            <span className="online" aria-hidden="true" />
            <span className="topbar-title">{activeTitle || 'Academy assistant'}</span>
            <span className="muted topbar-sub">Student support</span>
          </div>
        </header>

        <section className="stage" ref={stage} onScroll={onStageScroll}>
          {empty ? (
            <div className="welcome">
              <div className="welcome-icon"><Sparkles /></div>
              <h1>How can we help you today?</h1>
              <p>
                Ask about programs, admissions, schedules, payments, or anything else
                about your Academy experience.
              </p>
              <div className="suggestions">
                {SUGGESTIONS.map(({ icon: Icon, text }) => (
                  <button key={text} type="button" onClick={() => ask(text)}>
                    <Icon size={17} />
                    <span>{text}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="messages" role="log" aria-live="polite">
              {loading ? (
                <p className="loading-inline">Loading conversation…</p>
              ) : (
                messages.map((m, i) => (
                  <Message key={m.id ?? i} m={m} onDownload={downloadCitation} downloading={downloading} />
                ))
              )}
              {busy && (
                <div className="message">
                  <div className="bot-avatar"><Sparkles size={16} /></div>
                  <div className="bubble">
                    <span className="typing" role="status" aria-label="The assistant is typing">
                      <i /><i /><i />
                    </span>
                  </div>
                </div>
              )}
              <div ref={end} />
            </div>
          )}
        </section>

        {showJump && !empty && (
          <button type="button" className="jump" onClick={jumpToLatest}>
            <ArrowDown size={15} /> Latest
          </button>
        )}

        {error && (
          <div className="error chat-error" role="alert">
            <span>{error}</span>
            <div className="chat-error-actions">
              {failed && (
                <button type="button" onClick={() => ask(lastQuestion.current)}>
                  <RotateCw size={14} /> Try again
                </button>
              )}
              <button type="button" aria-label="Dismiss error" onClick={() => setError('')}>
                <X size={15} />
              </button>
            </div>
          </div>
        )}

        <div className="composer-wrap">
          <form className="composer" onSubmit={send}>
            <textarea
              ref={input}
              rows={1}
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
            Enter to send, Shift+Enter for a new line. Answers can contain mistakes, so check important details.
          </div>
        </div>
      </main>
    </div>
  );
}