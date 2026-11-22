const BASE=(import.meta.env.VITE_API_URL||'http://127.0.0.1:8000').replace(/\/$/,'');
export const token=()=>localStorage.getItem('concierge_token');
export const saveToken=value=>localStorage.setItem('concierge_token',value);
export const clearToken=()=>localStorage.removeItem('concierge_token');
export async function api(path,options={}){const headers={...(options.body?{'Content-Type':'application/json'}:{}),...(options.headers||{})};if(token())headers.Authorization=`Bearer ${token()}`;let res;try{res=await fetch(BASE+path,{...options,headers});}catch{throw Error('Cannot connect to the Academy server. Check that the backend is running.')}const data=await res.json().catch(()=>({}));if(!res.ok)throw Error(typeof data.detail==='string'?data.detail:`Request failed (${res.status})`);return data;}
export async function downloadDocument(documentId){const headers={};if(token())headers.Authorization=`Bearer ${token()}`;let res;try{res=await fetch(`${BASE}/documents/${documentId}/download`,{headers});}catch{throw Error('Cannot connect to the Academy server. Check that the backend is running.')}if(!res.ok){const data=await res.json().catch(()=>({}));throw Error(typeof data.detail==='string'?data.detail:`Download failed (${res.status})`)}const blob=await res.blob();const disposition=res.headers.get('content-disposition')||'';const match=disposition.match(/filename="?([^";]+)"?/i);const filename=match?.[1]||`document-${documentId}`;const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=filename;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
export const auth={checkEmail:email=>api('/users/check-email',{method:'POST',body:JSON.stringify({email})}),login:(email,password)=>api('/users/login',{method:'POST',body:JSON.stringify({email,password})}),register:(full_name,email,password)=>api('/users/register',{method:'POST',body:JSON.stringify({full_name,email,password})}),me:()=>api('/users/me')};
export const chats={list:()=>api('/conversations/'),create:()=>api('/conversations/',{method:'POST',body:JSON.stringify({channel:'website',language:navigator.language?.slice(0,2)||'en'})}),messages:id=>api(`/conversations/${id}/messages`),send:(conversation_id,question)=>api('/ai/chat',{method:'POST',body:JSON.stringify({conversation_id,question})}),remove:id=>api(`/conversations/${id}`,{method:'DELETE'})};
export const emailAssistant = {
  connection: () => api('/email-assistant/connection'),

  connect: () => api('/email-assistant/connect'),

  sync: () => api('/email-assistant/sync', {
    method: 'POST',
  }),

  messages: (status) =>
    api(`/email-assistant/messages${status ? `?status_filter=${encodeURIComponent(status)}` : ''}`),

  generateDraft: (id) =>
    api(`/email-assistant/messages/${id}/draft`, {
      method: 'POST',
    }),

  updateDraft: (id, reply_draft) =>
    api(`/email-assistant/messages/${id}/draft`, {
      method: 'PUT',
      body: JSON.stringify({ reply_draft }),
    }),

  approve: (id) =>
    api(`/email-assistant/messages/${id}/approve`, {
      method: 'POST',
    }),

  send: (id) =>
    api(`/email-assistant/messages/${id}/send`, {
      method: 'POST',
    }),
};
export const emailAssistant = {
  connection: () => api('/email-assistant/connection'),
  connect: () => api('/email-assistant/connect'),
  sync: () => api('/email-assistant/sync', { method: 'POST' }),
  messages: (status) =>
    api(`/email-assistant/messages${status ? `?status_filter=${encodeURIComponent(status)}` : ''}`),
  generateDraft: (id) =>
    api(`/email-assistant/messages/${id}/draft`, { method: 'POST' }),
  updateDraft: (id, reply_draft) =>
    api(`/email-assistant/messages/${id}/draft`, {
      method: 'PUT',
      body: JSON.stringify({ reply_draft }),
    }),
  approve: (id) =>
    api(`/email-assistant/messages/${id}/approve`, { method: 'POST' }),
  send: (id) =>
    api(`/email-assistant/messages/${id}/send`, { method: 'POST' }),
};