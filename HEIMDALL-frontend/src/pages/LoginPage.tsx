/**
 * HEIMDALL — Authentication gate.
 * Register (email+password) → OTP emailed → verify → dashboard.
 * "Continue with Google" available (requires OAuth config on the backend).
 */
import { useState, useRef, useEffect, useCallback } from 'react';
import toast from 'react-hot-toast';
import { ShieldCheck, Mail, KeyRound, User as UserIcon, Loader2, ArrowLeft, ArrowRight } from 'lucide-react';
import { authApi } from '@/services/api';
import { ShieldArt } from '@/components/art/Art';

const TOKEN_KEY = 'heimdall_token';
const EMAIL_KEY = 'heimdall_email';

/* Google "G" logo (official 4-color paths) */
function GoogleG() {
  return (
    <svg width="17" height="17" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
    </svg>
  );
}

type Step = 'auth' | 'otp';

export default function LoginPage({ onDone }: { onDone: () => void }) {
  const [mode, setMode]       = useState<'signin' | 'register'>('signin');
  const [step, setStep]       = useState<Step>('auth');
  const [email, setEmail]     = useState('');
  const [password, setPassword] = useState('');
  const [name, setName]       = useState('');
  const [otp, setOtp]         = useState(['', '', '', '', '', '']);
  const [busy, setBusy]       = useState(false);
  const [notice, setNotice]   = useState<string | null>(null);
  const [googleCfg, setGoogleCfg] = useState<'checking' | 'on' | 'off'>('checking');
  const otpRefs = useRef<(HTMLInputElement | null)[]>([]);
  const googleDiv = useRef<HTMLDivElement | null>(null);

  const handleGoogle = useCallback(async (credential: string) => {
    setBusy(true);
    try {
      const res = await authApi.google(credential);
      localStorage.setItem(TOKEN_KEY, res.token);
      localStorage.setItem(EMAIL_KEY, res.email);
      toast.success('Signed in with Google.');
      onDone();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Google sign-in failed.');
    } finally { setBusy(false); }
  }, [onDone]);

  /* Load Google Identity Services and render the official button */
  useEffect(() => {
    let cancelled = false;
    authApi.googleClientId().then(({ client_id }) => {
      if (cancelled || !client_id) { if (!cancelled) setGoogleCfg('off'); return; }
      const w = window as any;
      const init = () => {
        if (cancelled) return;
        w.google.accounts.id.initialize({
          client_id,
          callback: (resp: any) => handleGoogle(resp.credential),
        });
        if (googleDiv.current) {
          w.google.accounts.id.renderButton(googleDiv.current, {
            theme: 'outline', size: 'large', shape: 'pill',
            text: 'continue_with', width: 344, logo_alignment: 'left',
          });
        }
        setGoogleCfg('on');
      };
      if (w.google?.accounts?.id) init();
      else {
        const s = document.createElement('script');
        s.src = 'https://accounts.google.com/gsi/client';
        s.async = true;
        s.onload = init;
        s.onerror = () => { if (!cancelled) setGoogleCfg('off'); };
        document.head.appendChild(s);
      }
    }).catch(() => { if (!cancelled) setGoogleCfg('off'); });
    return () => { cancelled = true; };
  }, [handleGoogle]);

  const submitAuth = async () => {
    if (!email.trim() || !password) { toast.error('Enter your email and password.'); return; }
    setBusy(true);
    try {
      const res = mode === 'register'
        ? await authApi.register(email.trim(), password, name.trim() || undefined)
        : await authApi.login(email.trim(), password);
      setNotice(res.dev_otp
        ? `${res.message} Demo code: ${res.dev_otp}`
        : res.message);
      if (res.dev_otp) {
        toast(`SMTP not configured — using demo code ${res.dev_otp}`, { icon: '✉️' });
      } else {
        toast.success('Verification code sent to your email.');
      }
      setStep('otp');
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Authentication failed.');
    } finally { setBusy(false); }
  };

  const submitOtp = async () => {
    const code = otp.join('');
    if (code.length !== 6) { toast.error('Enter the 6-digit code.'); return; }
    setBusy(true);
    try {
      const res = await authApi.verifyOtp(email.trim(), code);
      localStorage.setItem(TOKEN_KEY, res.token);
      localStorage.setItem(EMAIL_KEY, res.email);
      toast.success('Welcome to HEIMDALL.');
      onDone();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Verification failed.');
    } finally { setBusy(false); }
  };

  const setOtpDigit = (i: number, v: string) => {
    const d = v.replace(/\D/g, '').slice(-1);
    const next = [...otp]; next[i] = d; setOtp(next);
    if (d && i < 5) otpRefs.current[i + 1]?.focus();
  };

  const inputCls = "w-full rounded-xl border border-[rgba(31,36,32,0.14)] bg-white/70 px-4 py-2.5 text-sm text-[#1F2420] outline-none transition-all placeholder:text-[#8A9080] focus:border-[#3F4A32] focus:ring-2 focus:ring-[#3F4A32]/15";

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-[420px]">
        {/* Brand */}
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-[#3F4A32] shadow-lg">
            <ShieldArt size={26} className="text-[#F8F9F6]" />
          </div>
          <div className="font-display text-[26px] font-bold uppercase tracking-[0.2em] text-[#1F2420]">Heimdall</div>
          <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.22em] text-[#8A9080]">
            AI Identity &amp; Document Screening
          </div>
        </div>

        <div className="panel p-7">
          {step === 'auth' ? (
            <>
              <h2 className="font-display text-[20px] font-semibold uppercase tracking-[0.1em] text-[#1F2420]">
                {mode === 'signin' ? 'Officer Sign In' : 'Create Account'}
              </h2>
              <p className="mt-1 text-xs leading-relaxed text-[#5A6153]">
                {mode === 'signin'
                  ? 'Sign in with your registered email. A one-time code will be sent to verify it is you.'
                  : 'Register with your email and a password. You will receive a one-time verification code.'}
              </p>

              {mode === 'register' && (
                <div className="mt-5">
                  <label className="field-label mb-1.5 block">Full Name</label>
                  <div className="relative">
                    <UserIcon size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#8A9080]" />
                    <input value={name} onChange={e => setName(e.target.value)} placeholder="Officer name"
                           className={`${inputCls} pl-10`} disabled={busy} />
                  </div>
                </div>
              )}

              <div className="mt-4">
                <label className="field-label mb-1.5 block">Email</label>
                <div className="relative">
                  <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#8A9080]" />
                  <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                         placeholder="you@karnavatiuniversity.edu.in" className={`${inputCls} pl-10`}
                         disabled={busy} onKeyDown={e => e.key === 'Enter' && submitAuth()} />
                </div>
              </div>

              <div className="mt-4">
                <label className="field-label mb-1.5 block">Password</label>
                <div className="relative">
                  <KeyRound size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#8A9080]" />
                  <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                         placeholder={mode === 'register' ? 'Minimum 8 characters' : 'Your password'}
                         className={`${inputCls} pl-10`} disabled={busy}
                         onKeyDown={e => e.key === 'Enter' && submitAuth()} />
                </div>
              </div>

              <button onClick={submitAuth} disabled={busy} className="btn-primary mt-6 w-full py-3">
                {busy
                  ? <><Loader2 size={15} className="animate-spin" />Please wait…</>
                  : <>{mode === 'signin' ? 'Send Verification Code' : 'Register & Send Code'}<ArrowRight size={15} /></>}
              </button>

              {/* Divider */}
              <div className="my-5 flex items-center gap-3">
                <span className="h-px flex-1 bg-[rgba(31,36,32,0.10)]" />
                <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#8A9080]">or</span>
                <span className="h-px flex-1 bg-[rgba(31,36,32,0.10)]" />
              </div>

              {googleCfg === 'off' ? (
                <button
                  onClick={() => toast('Google sign-in is not configured on this deployment. Ask the admin to set GOOGLE_CLIENT_ID.', { icon: '🔒' })}
                  className="btn-ghost w-full py-2.5"
                >
                  <GoogleG /> Continue with Google
                </button>
              ) : (
                <div className="flex justify-center" data-google-ready={googleCfg === 'on'}>
                  <div ref={googleDiv} />
                </div>
              )}

              <div className="mt-5 text-center text-xs text-[#5A6153]">
                {mode === 'signin' ? "Don't have an account? " : 'Already registered? '}
                <button
                  onClick={() => { setMode(mode === 'signin' ? 'register' : 'signin'); setNotice(null); }}
                  className="font-semibold text-[#3F4A32] underline decoration-[#3F4A32]/30 underline-offset-2 hover:decoration-[#3F4A32]"
                >
                  {mode === 'signin' ? 'Register' : 'Sign in'}
                </button>
              </div>
            </>
          ) : (
            /* ── OTP step ── */
            <>
              <button onClick={() => { setStep('auth'); setOtp(['','','','','','']); }}
                      className="mb-4 inline-flex items-center gap-1.5 text-xs font-medium text-[#5A6153] hover:text-[#3F4A32]">
                <ArrowLeft size={13} /> Back
              </button>
              <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-[#3F4A32]/10 text-[#3F4A32]">
                <ShieldCheck size={22} />
              </div>
              <h2 className="font-display text-[20px] font-semibold uppercase tracking-[0.1em] text-[#1F2420]">
                Verify Email
              </h2>
              <p className="mt-1 text-xs leading-relaxed text-[#5A6153]">
                Enter the 6-digit code sent to <strong className="text-[#1F2420]">{email}</strong>.
                The code is valid for 10 minutes.
              </p>

              {notice && (
                <div className="mt-3 rounded-lg border border-[#C47A2C]/30 bg-[#C47A2C]/[0.08] px-3.5 py-2.5 text-[11px] leading-relaxed text-[#8A5A1B]">
                  {notice}
                </div>
              )}

              <div className="mt-5 flex justify-between gap-2">
                {otp.map((d, i) => (
                  <input
                    key={i}
                    ref={el => { otpRefs.current[i] = el; }}
                    value={d}
                    onChange={e => setOtpDigit(i, e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Backspace' && !otp[i] && i > 0) otpRefs.current[i - 1]?.focus();
                      if (e.key === 'Enter' && otp.join('').length === 6) submitOtp();
                    }}
                    inputMode="numeric" autoFocus={i === 0} disabled={busy}
                    className="h-12 w-full max-w-[52px] rounded-xl border border-[rgba(31,36,32,0.14)] bg-white/80 text-center font-mono text-lg font-semibold text-[#1F2420] outline-none transition-all focus:border-[#3F4A32] focus:ring-2 focus:ring-[#3F4A32]/15"
                  />
                ))}
              </div>

              <button
                onClick={submitOtp} disabled={busy || otp.join('').length !== 6}
                className="btn-primary mt-6 w-full py-3"
              >
                {busy
                  ? <><Loader2 size={15} className="animate-spin" />Verifying…</>
                  : <>Verify &amp; Enter Dashboard<ArrowRight size={15} /></>}
              </button>

              <div className="mt-4 text-center text-xs text-[#5A6153]">
                Didn't receive it?{' '}
                <button onClick={() => setStep('auth')} className="font-semibold text-[#3F4A32] underline underline-offset-2">
                  Resend code
                </button>
              </div>
            </>
          )}
        </div>

        <div className="mt-5 text-center font-mono text-[10px] uppercase tracking-[0.18em] text-[#8A9080]">
          PS 26188 · MHA · SSB · SIH 2026
        </div>
      </div>
    </div>
  );
}
