import React, { useId, useState } from 'react';
import { ArrowRight, ArrowLeft, Eye, EyeOff, GraduationCap, Sparkles } from 'lucide-react';
import { auth, saveToken } from '../api';

function PasswordField({ label, value, onChange, placeholder, autoComplete, hint, invalid }) {
  const [shown, setShown] = useState(false);
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="password-wrap">
        <input
          id={id}
          type={shown ? 'text' : 'password'}
          minLength={8}
          required
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          autoComplete={autoComplete}
          aria-invalid={invalid || undefined}
        />
        <button
          type="button"
          className="toggle-pass"
          aria-label={shown ? 'Hide password' : 'Show password'}
          aria-pressed={shown}
          onClick={() => setShown((s) => !s)}
        >
          {shown ? <EyeOff size={17} /> : <Eye size={17} />}
        </button>
      </div>
      {hint && <span className={`hint ${invalid ? 'bad' : ''}`}>{hint}</span>}
    </div>
  );
}

function SubmitButton({ busy, children }) {
  return (
    <button className="primary" disabled={busy}>
      {busy ? <span className="spinner" aria-hidden="true" /> : null}
      {children}
      {!busy && <ArrowRight size={17} />}
    </button>
  );
}

const COPY = {
  email: { title: 'Welcome to the Academy', sub: 'Enter your email address to continue.' },
  login: { title: 'Welcome back', sub: 'Enter your password to sign in.' },
  register: { title: 'Create your account', sub: 'We don’t have an account for this email yet. Create one to start chatting.' },
};

export default function AuthScreen({ onLogin }) {
  const [step, setStep] = useState('email');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const mismatch = step === 'register' && confirm.length > 0 && confirm !== password;

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
      setError('The passwords don’t match.');
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

  const { title, sub } = COPY[step];

  return (
    <main className="auth">
      <section className="brand-side">
        <div className="logo">
          <span className="mark"><GraduationCap /></span>Academy <i>Concierge</i>
        </div>
        <div className="brand-copy">
          <h1>Guidance that moves you forward.</h1>
          <p>Ask questions, explore programs, and get support throughout your Academy journey.</p>
          <div className="tagline"><Sparkles size={16} /> Your personal Academy assistant</div>
        </div>
      </section>

      <section className="auth-side">
        <div className="auth-card">
          <div className="mobile-logo">
            <span className="mark"><GraduationCap /></span> Academy Concierge
          </div>
          <h2>{title}</h2>
          <p className="sub">{sub}</p>

          {step === 'email' ? (
            <form onSubmit={continueWithEmail}>
              <div className="field">
                <label htmlFor="auth-email">Email address</label>
                <input
                  id="auth-email"
                  type="email"
                  required
                  autoFocus
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  autoComplete="email"
                />
              </div>
              {error && <div className="error" role="alert">{error}</div>}
              <SubmitButton busy={busy}>{busy ? 'Checking…' : 'Continue'}</SubmitButton>
            </form>
          ) : (
            <form onSubmit={submitAccount}>
              <div className="email-pill">
                <span>{email}</span>
                <button type="button" onClick={back}><ArrowLeft size={14} /> Change</button>
              </div>
              {step === 'register' && (
                <div className="field">
                  <label htmlFor="auth-name">Full name</label>
                  <input
                    id="auth-name"
                    required
                    autoFocus
                    minLength={2}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Your full name"
                    autoComplete="name"
                  />
                </div>
              )}
              <PasswordField
                label={step === 'register' ? 'Create password' : 'Password'}
                value={password}
                onChange={setPassword}
                placeholder={step === 'register' ? 'At least 8 characters' : 'Enter your password'}
                autoComplete={step === 'register' ? 'new-password' : 'current-password'}
                hint={step === 'register' ? 'Use at least 8 characters.' : undefined}
              />
              {step === 'register' && (
                <PasswordField
                  label="Confirm password"
                  value={confirm}
                  onChange={setConfirm}
                  placeholder="Re-enter your password"
                  autoComplete="new-password"
                  invalid={mismatch}
                  hint={mismatch ? 'The passwords don’t match.' : undefined}
                />
              )}
              {error && <div className="error" role="alert">{error}</div>}
              <SubmitButton busy={busy}>
                {busy ? 'Please wait…' : step === 'login' ? 'Sign in' : 'Create account'}
              </SubmitButton>
            </form>
          )}
        </div>
      </section>
    </main>
  );
}