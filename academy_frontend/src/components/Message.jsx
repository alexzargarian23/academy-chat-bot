import React, { useState } from 'react';
import { Check, Copy, FileText, LifeBuoy, Sparkles, UserRound } from 'lucide-react';
import { asArray, timeLabel } from '../utils';

/* ---------- tiny markdown renderer (no dependency) ---------- */

// bold | code | [text](url) | [Source 1] / [Source 1, page 3] / 【…】
const INLINE =
  /(\*\*[^*]+\*\*)|(`[^`]+`)|(\[([^\]]+)\]\((https?:\/\/[^)\s]+)\))|([\[【]Source\s+(\d+)(?:,\s*page\s+([^\]】]+))?[\]】])/gi;

function renderInline(text, ctx, prefix) {
  const out = [];
  let last = 0;
  let m;
  const re = new RegExp(INLINE.source, 'gi');
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const key = `${prefix}-${m.index}`;
    if (m[1]) {
      out.push(<strong key={key}>{m[1].slice(2, -2)}</strong>);
    } else if (m[2]) {
      out.push(<code key={key}>{m[2].slice(1, -1)}</code>);
    } else if (m[3]) {
      out.push(
        <a key={key} href={m[5]} target="_blank" rel="noopener noreferrer">{m[4]}</a>
      );
    } else {
      const source = ctx.sourceMap.get(m[7]);
      if (source?.document_id && source.can_download !== false) {
        const busy = ctx.downloading === source.document_id;
        out.push(
          <button
            key={key}
            type="button"
            className="citation"
            disabled={busy}
            onClick={() => ctx.onDownload(source)}
            title={`Download ${source.document_title || 'source document'}`}
          >
            {busy ? 'Downloading…' : m[6]}
          </button>
        );
      } else {
        out.push(m[6]);
      }
    }
    last = re.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const UL = /^\s*[-*•]\s+/;
const OL = /^\s*\d+[.)]\s+/;
const HEAD = /^#{1,4}\s+/;

function parseBlocks(text) {
  const lines = text.replace(/\r\n/g, '\n').split('\n');
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (/^```/.test(line)) {
      const code = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) code.push(lines[i++]);
      i++;
      blocks.push({ type: 'code', text: code.join('\n') });
    } else if (UL.test(line)) {
      const items = [];
      while (i < lines.length && UL.test(lines[i])) items.push(lines[i++].replace(UL, ''));
      blocks.push({ type: 'ul', items });
    } else if (OL.test(line)) {
      const items = [];
      while (i < lines.length && OL.test(lines[i])) items.push(lines[i++].replace(OL, ''));
      blocks.push({ type: 'ol', items });
    } else if (HEAD.test(line)) {
      blocks.push({ type: 'h', text: line.replace(HEAD, '') });
      i++;
    } else if (!line.trim()) {
      i++;
    } else {
      const para = [];
      while (
        i < lines.length && lines[i].trim() &&
        !/^```/.test(lines[i]) && !UL.test(lines[i]) && !OL.test(lines[i]) && !HEAD.test(lines[i])
      ) para.push(lines[i++]);
      blocks.push({ type: 'p', text: para.join('\n') });
    }
  }
  return blocks;
}

function Markdown({ content, sources, onDownload, downloading }) {
  const ctx = {
    onDownload,
    downloading,
    sourceMap: new Map(
      asArray(sources).map((s, i) => [String(s.source_id ?? i + 1), s])
    ),
  };
  return parseBlocks(content ?? '').map((b, i) => {
    const k = `b${i}`;
    switch (b.type) {
      case 'code': return <pre key={k}><code>{b.text}</code></pre>;
      case 'h': return <p key={k} className="md-heading">{renderInline(b.text, ctx, k)}</p>;
      case 'ul': return <ul key={k}>{b.items.map((t, j) => <li key={j}>{renderInline(t, ctx, `${k}-${j}`)}</li>)}</ul>;
      case 'ol': return <ol key={k}>{b.items.map((t, j) => <li key={j}>{renderInline(t, ctx, `${k}-${j}`)}</li>)}</ol>;
      default: return <p key={k}>{renderInline(b.text, ctx, k)}</p>;
    }
  });
}

/* ---------- message ---------- */

function SourceChips({ content, sources, onDownload, downloading }) {
  // Only documents the answer actually cites, e.g. [Source 2]
  const cited = new Set(
    [...(content ?? '').matchAll(/[\[【]Source\s+(\d+)/gi)].map((m) => m[1])
  );
  const seen = new Set();
  const unique = asArray(sources).filter((s, i) => {
    const id = String(s.source_id ?? i + 1);
    if (!cited.has(id) || !s.document_id || s.can_download === false) return false;
    if (seen.has(s.document_id)) return false;
    seen.add(s.document_id);
    return true;
  });
  if (!unique.length) return null;
  return (
    <div className="sources" aria-label="Sources">
      {unique.map((s) => (
        <button
          key={s.document_id}
          type="button"
          className="source-chip"
          disabled={downloading === s.document_id}
          onClick={() => onDownload(s)}
          title="Download source document"
        >
          <FileText size={14} />
          <span>{downloading === s.document_id ? 'Downloading…' : s.document_title || 'Source document'}</span>
        </button>
      ))}
    </div>
  );
}

export default function Message({ m, message, onDownload, downloading }) {
  const msg = m ?? message; // accept either prop name
  const [copied, setCopied] = useState(false);
  if (!msg) return null;
  const mine = msg.sender === 'user';

  async function copy() {
    try {
      await navigator.clipboard.writeText(msg.content ?? '');
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard blocked */ }
  }

  return (
    <div className={`message ${mine ? 'mine' : ''}`}>
      {!mine && <div className="bot-avatar"><Sparkles size={16} /></div>}
      <div className="message-body">
        <div className="meta">
          {mine ? 'You' : 'Academy assistant'}
          <time>{timeLabel(msg.created_at)}</time>
        </div>
        <div className="bubble">
          {mine ? msg.content : (
            <Markdown content={msg.content} sources={msg.sources} onDownload={onDownload} downloading={downloading} />
          )}
        </div>
        {!mine && <SourceChips content={msg.content} sources={msg.sources} onDownload={onDownload} downloading={downloading} />}
        {msg.handoff_required && (
          <div className="handoff">
            <LifeBuoy size={15} />
            <span>This request has been flagged for a member of the Academy team to follow up.</span>
          </div>
        )}
        {!mine && (
          <div className="msg-actions">
            <button type="button" onClick={copy} aria-label="Copy answer">
              {copied ? <Check size={14} /> : <Copy size={14} />}
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
        )}
      </div>
      {mine && <div className="user-avatar"><UserRound size={16} /></div>}
    </div>
  );
}