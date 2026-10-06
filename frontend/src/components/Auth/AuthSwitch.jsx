import React, { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { 
  Mail, 
  Lock, 
  User, 
  Eye, 
  EyeOff, 
  ArrowRight, 
  Sparkles, 
  CheckCircle2, 
  AlertCircle, 
  X, 
  KeyRound, 
  ArrowLeft, 
  ShieldCheck
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import logo from '../../assets/logo.png';

export const AuthSwitch = ({ 
  initialMode = 'login', 
  onToggleMode, 
  onSuccess, 
  notice = '', 
  onNoticeDismiss 
}) => {
  const [isSignUp, setIsSignUp] = useState(initialMode === 'register');

  // Sync mode if initialMode prop updates from external navigation
  useEffect(() => {
    setIsSignUp(initialMode === 'register');
  }, [initialMode]);

  const { login, register } = useAuth();

  // Sign In Form State
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [showLoginPassword, setShowLoginPassword] = useState(false);
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState('');

  // Sign Up Form State
  const [regName, setRegName] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [regConfirmPassword, setRegConfirmPassword] = useState('');
  const [showRegPassword, setShowRegPassword] = useState(false);
  const [showRegConfirmPassword, setShowRegConfirmPassword] = useState(false);
  const [regLoading, setRegLoading] = useState(false);
  const [regError, setRegError] = useState('');
  const [passwordStrength, setPasswordStrength] = useState(0);

  // Forgot Password Modal State
  const [showForgotModal, setShowForgotModal] = useState(false);
  const [forgotEmail, setForgotEmail] = useState('');
  const [forgotStatus, setForgotStatus] = useState({ loading: false, success: false, msg: '' });

  // Calculate password strength
  useEffect(() => {
    let score = 0;
    if (!regPassword) {
      setPasswordStrength(0);
      return;
    }
    if (regPassword.length >= 6) score += 1;
    if (/[A-Z]/.test(regPassword)) score += 1;
    if (/[0-9]/.test(regPassword)) score += 1;
    if (/[^A-Za-z0-9]/.test(regPassword)) score += 1;
    setPasswordStrength(score);
  }, [regPassword]);

  // Handle Login Submit
  const handleLoginSubmit = async (e) => {
    e.preventDefault();
    setLoginError('');

    if (!loginEmail || !loginPassword) {
      setLoginError('Please enter both your email and password.');
      return;
    }

    setLoginLoading(true);
    try {
      await login(loginEmail, loginPassword);
      if (onNoticeDismiss) onNoticeDismiss();
      if (onSuccess) onSuccess(false);
    } catch (err) {
      setLoginError(err.message || 'Invalid email or password. Please try again.');
    } finally {
      setLoginLoading(false);
    }
  };

  // Handle Sign Up Submit
  const handleRegisterSubmit = async (e) => {
    e.preventDefault();
    setRegError('');

    if (!regName || !regEmail || !regPassword || !regConfirmPassword) {
      setRegError('Please complete all required fields.');
      return;
    }

    if (regPassword.length < 6) {
      setRegError('Password must contain at least 6 characters.');
      return;
    }

    if (regPassword !== regConfirmPassword) {
      setRegError('Passwords do not match.');
      return;
    }

    setRegLoading(true);
    try {
      await register(regName, regEmail, regPassword);
      if (onSuccess) onSuccess(true);
      else if (onToggleMode) onToggleMode('dashboard');
    } catch (err) {
      setRegError(err.message || 'Registration failed. Please try a different email address.');
    } finally {
      setRegLoading(false);
    }
  };

  // Handle Forgot Password
  const handleForgotSubmit = (e) => {
    e.preventDefault();
    if (!forgotEmail) {
      setForgotStatus({ loading: false, success: false, msg: 'Please enter your registered email address.' });
      return;
    }

    setForgotStatus({ loading: true, success: false, msg: '' });
    setTimeout(() => {
      setForgotStatus({
        loading: false,
        success: true,
        msg: `A secure password reset link has been dispatched to ${forgotEmail}. Please check your inbox.`,
      });
    }, 1000);
  };

  const getStrengthLabel = () => {
    switch (passwordStrength) {
      case 0: return 'Too Weak';
      case 1: return 'Weak';
      case 2: return 'Medium';
      case 3: return 'Strong';
      case 4: return 'Very Strong';
      default: return 'Weak';
    }
  };

  const getStrengthColor = () => {
    switch (passwordStrength) {
      case 0: return 'bg-slate-200';
      case 1: return 'bg-red-500';
      case 2: return 'bg-amber-500';
      case 3: return 'bg-emerald-500';
      case 4: return 'bg-emerald-600';
      default: return 'bg-slate-200';
    }
  };

  return (
    <div className="min-h-screen w-full flex flex-col justify-between py-6 px-4 sm:px-6 lg:px-8 bg-[#F8FAFC] relative overflow-hidden font-sans text-slate-900 select-none">
      
      {/* ═══════════════════════════════════════════════════════════ */}
      {/* SUBTLE PROFESSIONAL AMBIENT BACKDROP                        */}
      {/* ═══════════════════════════════════════════════════════════ */}
      <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden" aria-hidden="true">
        <div className="absolute top-[-10%] left-[-8%] w-[550px] h-[550px] bg-brand-500/[0.04] rounded-full blur-[100px]" />
        <div className="absolute bottom-[-10%] right-[-8%] w-[600px] h-[600px] bg-indigo-500/[0.04] rounded-full blur-[110px]" />
        <div 
          className="absolute inset-0 opacity-[0.025]"
          style={{ 
            backgroundImage: 'radial-gradient(#0F172A 1px, transparent 1px)', 
            backgroundSize: '28px 28px' 
          }} 
        />
      </div>

      {/* ═══════════════════════════════════════════════════════════════════════ */}
      {/* TOP CENTER FLOATING ALERT TOAST (SESSION NOTICE / ERROR MESSAGES)      */}
      {/* ═══════════════════════════════════════════════════════════════════════ */}
      <div className="fixed top-6 left-1/2 -translate-x-1/2 z-50 w-full max-w-md px-4 pointer-events-none flex flex-col items-center gap-2">
        <AnimatePresence>
          {/* Active Error Alert */}
          {(loginError || regError) && (
            <motion.div
              initial={{ opacity: 0, y: -20, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -20, scale: 0.95 }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              className="pointer-events-auto w-full p-3.5 bg-red-50/95 backdrop-blur-md border border-red-200 text-red-700 text-xs rounded-2xl font-semibold shadow-lg shadow-red-500/10 flex items-center justify-between gap-3"
            >
              <div className="flex items-center gap-2.5">
                <AlertCircle className="w-4 h-4 shrink-0 text-red-500" />
                <span>{loginError || regError}</span>
              </div>
              <button
                type="button"
                onClick={() => {
                  setLoginError('');
                  setRegError('');
                }}
                className="text-red-400 hover:text-red-700 p-1 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </motion.div>
          )}

          {/* Active Session Notice */}
          {notice && (
            <motion.div
              initial={{ opacity: 0, y: -20, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -20, scale: 0.95 }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              className="pointer-events-auto w-full p-3.5 bg-amber-50/95 backdrop-blur-md border border-amber-200 text-amber-900 text-xs rounded-2xl font-semibold shadow-lg shadow-amber-500/10 flex items-center justify-between gap-3"
            >
              <div className="flex items-center gap-2.5">
                <AlertCircle className="w-4 h-4 shrink-0 text-amber-500" />
                <span>{notice}</span>
              </div>
              {onNoticeDismiss && (
                <button
                  type="button"
                  onClick={onNoticeDismiss}
                  className="text-amber-600 hover:text-amber-900 p-1 cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ── Top Header ── */}
      <header className="max-w-6xl mx-auto w-full flex justify-between items-center z-10 relative mb-3">
        <button 
          onClick={() => onToggleMode && onToggleMode('landing')} 
          title="Return to Home" 
          className="cursor-pointer rounded-2xl transition hover:opacity-90 active:scale-95 flex items-center gap-2.5 group"
        >
          <img src={logo} alt="RapidDoc Logo" className="w-[42px] h-[42px] object-contain drop-shadow-xs" />
          <span className="font-extrabold text-slate-900 text-xl tracking-tight">RapidDoc</span>
        </button>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setIsSignUp(!isSignUp)}
            className="hidden sm:inline-flex items-center gap-1.5 text-xs font-bold text-brand-600 hover:text-brand-700 bg-brand-50 hover:bg-brand-100/70 border border-brand-200/80 px-3.5 py-2 rounded-xl shadow-2xs transition-all cursor-pointer"
          >
            {isSignUp ? 'Switch to Sign In' : 'Switch to Create Account'}
          </button>
          
          <button
            onClick={() => onToggleMode && onToggleMode('landing')}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-brand-600 bg-white/80 hover:bg-white border border-slate-200/80 px-3.5 py-2 rounded-xl shadow-2xs transition-all cursor-pointer"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Home
          </button>
        </div>
      </header>

      {/* ═══════════════════════════════════════════════════════════════════════ */}
      {/* SLIDING AUTH CONTAINER WITH GROUND LIGHT ROTATING SHADOW AURA         */}
      {/* ═══════════════════════════════════════════════════════════════════════ */}
      <main className="w-full flex-grow flex items-center justify-center py-2 z-10 relative">
        <div className="relative w-full max-w-[960px] flex items-center justify-center">

          {/* ── Rotating Light-Colored Ground Aura Behind Container ── */}
          <div className="absolute -inset-8 sm:-inset-10 pointer-events-none -z-10 flex items-center justify-center overflow-visible">
            {/* Primary Smooth Rotating Light Shadow */}
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 14, repeat: Infinity, ease: 'linear' }}
              className="w-[122%] h-[122%] rounded-[70px] opacity-75 blur-[55px] sm:blur-[65px]"
              style={{
                background: 'conic-gradient(from 0deg at 50% 50%, rgba(56, 189, 248, 0.45) 0deg, rgba(99, 102, 241, 0.35) 90deg, rgba(168, 85, 247, 0.32) 180deg, rgba(45, 212, 191, 0.35) 270deg, rgba(56, 189, 248, 0.45) 360deg)',
              }}
            />
            {/* Secondary Counter-Rotating Pulse for Ground Depth */}
            <motion.div
              animate={{ rotate: -360, scale: [0.96, 1.04, 0.96] }}
              transition={{ 
                rotate: { duration: 20, repeat: Infinity, ease: 'linear' },
                scale: { duration: 7, repeat: Infinity, ease: 'easeInOut' }
              }}
              className="absolute w-[110%] h-[110%] rounded-[60px] opacity-60 blur-[45px]"
              style={{
                background: 'conic-gradient(from 180deg at 50% 50%, rgba(147, 197, 253, 0.35) 0deg, rgba(196, 181, 253, 0.35) 120deg, rgba(110, 231, 183, 0.28) 240deg, rgba(147, 197, 253, 0.35) 360deg)',
              }}
            />
          </div>

          {/* ── Main Sliding Card Shell ── */}
          <div className={`rd-auth-container ${isSignUp ? 'sign-up-mode' : ''}`}>
            
            {/* Forms Layer */}
            <div className="rd-forms-container">
              <div className="rd-signin-signup">
                
                {/* ── Sign In Form ── */}
                <form className="rd-form rd-sign-in-form" onSubmit={handleLoginSubmit}>
                  <div className="text-center mb-5">
                    <div className="inline-flex items-center justify-center w-11 h-11 rounded-2xl bg-brand-50 border border-brand-100 text-brand-600 mb-2.5 shadow-2xs">
                      <Lock className="w-5 h-5 stroke-[2.2]" />
                    </div>
                    <h2 className="text-2xl sm:text-[26px] font-extrabold text-slate-900 tracking-tight">
                      Sign in to RapidDoc
                    </h2>
                    <p className="text-xs text-slate-500 font-medium mt-1">
                      Welcome back! Enter your credentials to access your docs.
                    </p>
                  </div>

                  {/* Email Input */}
                  <div className="rd-input-field">
                    <Mail className="w-4 h-4 text-slate-400 shrink-0" />
                    <input 
                      type="email" 
                      placeholder="name@work-email.com" 
                      value={loginEmail}
                      onChange={(e) => setLoginEmail(e.target.value)}
                      required 
                    />
                  </div>

                  {/* Password Input */}
                  <div className="rd-input-field">
                    <Lock className="w-4 h-4 text-slate-400 shrink-0" />
                    <input 
                      type={showLoginPassword ? 'text' : 'password'} 
                      placeholder="Enter your password" 
                      value={loginPassword}
                      onChange={(e) => setLoginPassword(e.target.value)}
                      required 
                    />
                    <button
                      type="button"
                      onClick={() => setShowLoginPassword(!showLoginPassword)}
                      className="text-slate-400 hover:text-slate-600 focus:outline-none p-1 cursor-pointer"
                    >
                      {showLoginPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>

                  {/* Forgot Password Link */}
                  <div className="w-full max-w-[360px] flex justify-end mt-1 mb-2">
                    <button
                      type="button"
                      onClick={() => {
                        setForgotStatus({ loading: false, success: false, msg: '' });
                        setForgotEmail(loginEmail);
                        setShowForgotModal(true);
                      }}
                      className="text-xs font-semibold text-brand-600 hover:text-brand-700 hover:underline cursor-pointer"
                    >
                      Forgot password?
                    </button>
                  </div>

                  {/* Submit Button */}
                  <button 
                    type="submit" 
                    disabled={loginLoading}
                    className="rd-btn rd-btn-solid"
                  >
                    {loginLoading ? (
                      <div className="flex items-center justify-center gap-2">
                        <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                        <span>Authenticating...</span>
                      </div>
                    ) : (
                      <div className="flex items-center justify-center gap-1.5">
                        <span>Sign In</span>
                        <ArrowRight className="w-4 h-4" />
                      </div>
                    )}
                  </button>

                  <p className="rd-social-text">Or continue with</p>
                  <div className="rd-social-media">
                    <SocialIcons />
                  </div>
                </form>

                {/* ── Sign Up Form ── */}
                <form className="rd-form rd-sign-up-form" onSubmit={handleRegisterSubmit}>
                  <div className="text-center mb-4">
                    <div className="inline-flex items-center justify-center w-11 h-11 rounded-2xl bg-indigo-50 border border-indigo-100 text-indigo-600 mb-2 shadow-2xs">
                      <Sparkles className="w-5 h-5 stroke-[2.2]" />
                    </div>
                    <h2 className="text-2xl sm:text-[25px] font-extrabold text-slate-900 tracking-tight">
                      Create your account
                    </h2>
                    <p className="text-xs text-slate-500 font-medium mt-0.5">
                      Get started with intelligent document creation.
                    </p>
                  </div>

                  {/* Full Name Input */}
                  <div className="rd-input-field">
                    <User className="w-4 h-4 text-slate-400 shrink-0" />
                    <input 
                      type="text" 
                      placeholder="Full Name" 
                      value={regName}
                      onChange={(e) => setRegName(e.target.value)}
                      required 
                    />
                  </div>

                  {/* Email Input */}
                  <div className="rd-input-field">
                    <Mail className="w-4 h-4 text-slate-400 shrink-0" />
                    <input 
                      type="email" 
                      placeholder="Work email address" 
                      value={regEmail}
                      onChange={(e) => setRegEmail(e.target.value)}
                      required 
                    />
                  </div>

                  {/* Password Input */}
                  <div className="rd-input-field">
                    <Lock className="w-4 h-4 text-slate-400 shrink-0" />
                    <input 
                      type={showRegPassword ? 'text' : 'password'} 
                      placeholder="Create password" 
                      value={regPassword}
                      onChange={(e) => setRegPassword(e.target.value)}
                      required 
                    />
                    <button
                      type="button"
                      onClick={() => setShowRegPassword(!showRegPassword)}
                      className="text-slate-400 hover:text-slate-600 focus:outline-none p-1 cursor-pointer"
                    >
                      {showRegPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>

                  {/* Confirm Password Input */}
                  <div className="rd-input-field">
                    <ShieldCheck className="w-4 h-4 text-slate-400 shrink-0" />
                    <input 
                      type={showRegConfirmPassword ? 'text' : 'password'} 
                      placeholder="Confirm password" 
                      value={regConfirmPassword}
                      onChange={(e) => setRegConfirmPassword(e.target.value)}
                      required 
                    />
                    <button
                      type="button"
                      onClick={() => setShowRegConfirmPassword(!showRegConfirmPassword)}
                      className="text-slate-400 hover:text-slate-600 focus:outline-none p-1 cursor-pointer"
                    >
                      {showRegConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>

                  {/* Password Strength Indicator */}
                  {regPassword && (
                    <div className="w-full max-w-[360px] mt-1 mb-2">
                      <div className="flex justify-between items-center mb-1">
                        <span className="text-[10px] text-slate-400 font-semibold uppercase">Strength</span>
                        <span className="text-[11px] font-bold text-slate-600">{getStrengthLabel()}</span>
                      </div>
                      <div className="grid grid-cols-4 gap-1.5 h-1.5 w-full bg-slate-100 rounded-full overflow-hidden p-0.5">
                        <div className={`h-full rounded-full transition-all duration-300 ${passwordStrength >= 1 ? getStrengthColor() : 'bg-transparent'}`} />
                        <div className={`h-full rounded-full transition-all duration-300 ${passwordStrength >= 2 ? getStrengthColor() : 'bg-transparent'}`} />
                        <div className={`h-full rounded-full transition-all duration-300 ${passwordStrength >= 3 ? getStrengthColor() : 'bg-transparent'}`} />
                        <div className={`h-full rounded-full transition-all duration-300 ${passwordStrength >= 4 ? getStrengthColor() : 'bg-transparent'}`} />
                      </div>
                    </div>
                  )}

                  {/* Submit Button */}
                  <button 
                    type="submit" 
                    disabled={regLoading}
                    className="rd-btn rd-btn-solid mt-2"
                  >
                    {regLoading ? (
                      <div className="flex items-center justify-center gap-2">
                        <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                        <span>Creating Account...</span>
                      </div>
                    ) : (
                      <div className="flex items-center justify-center gap-1.5">
                        <span>Get Started Free</span>
                        <ArrowRight className="w-4 h-4" />
                      </div>
                    )}
                  </button>

                  <p className="rd-social-text">Or register with</p>
                  <div className="rd-social-media">
                    <SocialIcons />
                  </div>
                </form>

              </div>
            </div>

            {/* ── Overlay Panels Container ── */}
            <div className="rd-panels-container">
              
              {/* Left Panel (Shown when on Sign In mode, invites to Sign Up) */}
              <div className="rd-panel rd-left-panel">
                <div className="rd-panel-content">
                  <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-white/15 backdrop-blur-md border border-white/30 text-white mb-4 shadow-sm">
                    <Sparkles className="w-6 h-6" />
                  </div>
                  <h3>New to RapidDoc?</h3>
                  <p>
                    Transform raw briefs, meeting notes, and research into polished, publication-ready documents with AI.
                  </p>
                  <button
                    type="button"
                    className="rd-btn rd-btn-transparent"
                    onClick={() => setIsSignUp(true)}
                  >
                    Create Account
                  </button>
                </div>
              </div>

              {/* Right Panel (Shown when on Sign Up mode, invites to Sign In) */}
              <div className="rd-panel rd-right-panel">
                <div className="rd-panel-content">
                  <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-white/15 backdrop-blur-md border border-white/30 text-white mb-4 shadow-sm">
                    <CheckCircle2 className="w-6 h-6" />
                  </div>
                  <h3>Already a Member?</h3>
                  <p>
                    Log back into your RapidDoc workspace to manage your documents, models, and shared team exports.
                  </p>
                  <button
                    type="button"
                    className="rd-btn rd-btn-transparent"
                    onClick={() => setIsSignUp(false)}
                  >
                    Sign In
                  </button>
                </div>
              </div>

            </div>

          </div>

        </div>
      </main>

      {/* ═══════════════════════════════════════════════════ */}
      {/* FOOTER                                              */}
      {/* ═══════════════════════════════════════════════════ */}
      <footer className="max-w-6xl mx-auto w-full flex flex-col sm:flex-row items-center justify-between gap-2.5 pt-3 text-xs text-slate-500 font-medium z-10 relative">
        <div className="flex items-center gap-2">
          <span>© {new Date().getFullYear()} RapidDoc AI Technologies</span>
          <span className="text-slate-300">•</span>
          <span className="text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200 font-semibold text-[11px] inline-flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            SOC-2 Type II Certified
          </span>
        </div>
        <div className="flex items-center gap-4">
          <a href="#privacy" className="hover:text-slate-700 transition">Privacy Policy</a>
          <a href="#terms" className="hover:text-slate-700 transition">Terms of Service</a>
          <a href="#security" className="hover:text-slate-700 transition">Security</a>
        </div>
      </footer>

      {/* ═══════════════════════════════════════════════════════════════════════ */}
      {/* FORGOT PASSWORD MODAL DIALOG                                          */}
      {/* ═══════════════════════════════════════════════════════════════════════ */}
      <AnimatePresence>
        {showForgotModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="w-full max-w-md bg-white rounded-3xl p-7 shadow-2xl border border-slate-200 text-left relative"
            >
              <button
                onClick={() => setShowForgotModal(false)}
                className="absolute top-5 right-5 p-1.5 rounded-xl text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>

              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-2xl bg-brand-50 border border-brand-100 text-brand-600 flex items-center justify-center shadow-2xs">
                  <KeyRound className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-slate-900">Reset Password</h3>
                  <p className="text-xs text-slate-500">We will send a recovery link to your inbox</p>
                </div>
              </div>

              {forgotStatus.success ? (
                <div className="p-4 bg-emerald-50 border border-emerald-200 text-emerald-900 text-xs rounded-2xl font-medium mb-4 flex items-start gap-2.5">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                  <div>
                    <p className="font-bold mb-1">Check your inbox</p>
                    <p className="text-emerald-800">{forgotStatus.msg}</p>
                  </div>
                </div>
              ) : (
                <form onSubmit={handleForgotSubmit} className="space-y-4">
                  {forgotStatus.msg && (
                    <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-xs rounded-xl font-medium">
                      {forgotStatus.msg}
                    </div>
                  )}

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1.5">Registered Email</label>
                    <div className="relative">
                      <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
                      <input
                        type="email"
                        placeholder="you@company.com"
                        value={forgotEmail}
                        onChange={(e) => setForgotEmail(e.target.value)}
                        className="w-full pl-10 pr-4 py-2.5 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:border-brand-500 focus:ring-2 focus:ring-brand-500/10 outline-none transition"
                        required
                      />
                    </div>
                  </div>

                  <div className="flex items-center justify-end gap-2.5 pt-2">
                    <button
                      type="button"
                      onClick={() => setShowForgotModal(false)}
                      className="px-4 py-2.5 text-xs font-semibold text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-xl transition cursor-pointer"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={forgotStatus.loading}
                      className="px-5 py-2.5 text-xs font-bold text-white bg-brand-600 hover:bg-brand-700 rounded-xl shadow-xs transition cursor-pointer"
                    >
                      {forgotStatus.loading ? 'Sending link...' : 'Send Reset Link'}
                    </button>
                  </div>
                </form>
              )}
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ═══════════════════════════════════════════════════════════════════════ */}
      {/* HIGH-PERFORMANCE GPU-ACCELERATED SLIDING ANIMATION STYLES             */}
      {/* ═══════════════════════════════════════════════════════════════════════ */}
      <style>{`
        .rd-auth-container {
          position: relative;
          width: 100%;
          max-width: 960px;
          height: 610px;
          background: #FFFFFF;
          border-radius: 32px;
          box-shadow: 0 25px 60px -15px rgba(54, 92, 255, 0.16), 0 8px 24px rgba(15, 23, 42, 0.05);
          border: 1px solid rgba(226, 232, 240, 0.95);
          overflow: hidden;
        }

        .rd-forms-container {
          position: absolute;
          width: 100%;
          height: 100%;
          top: 0;
          left: 0;
        }

        .rd-signin-signup {
          position: absolute;
          top: 50%;
          transform: translate(-50%, -50%);
          left: 75%;
          width: 50%;
          transition: left 1.1s cubic-bezier(0.77, 0, 0.175, 1);
          display: grid;
          grid-template-columns: 1fr;
          z-index: 5;
        }

        .rd-auth-container.sign-up-mode .rd-signin-signup {
          left: 25%;
        }

        .rd-form {
          display: flex;
          align-items: center;
          justify-content: center;
          flex-direction: column;
          padding: 0 3.5rem;
          transition: opacity 0.5s ease-in-out, transform 0.6s cubic-bezier(0.77, 0, 0.175, 1);
          overflow: hidden;
          grid-column: 1 / 2;
          grid-row: 1 / 2;
          width: 100%;
        }

        .rd-form.rd-sign-in-form {
          opacity: 1;
          z-index: 2;
          pointer-events: all;
          transform: scale(1);
        }

        .rd-form.rd-sign-up-form {
          opacity: 0;
          z-index: 1;
          pointer-events: none;
          transform: scale(0.96);
        }

        .rd-auth-container.sign-up-mode .rd-form.rd-sign-in-form {
          opacity: 0;
          z-index: 1;
          pointer-events: none;
          transform: scale(0.96);
        }

        .rd-auth-container.sign-up-mode .rd-form.rd-sign-up-form {
          opacity: 1;
          z-index: 2;
          pointer-events: all;
          transform: scale(1);
        }

        .rd-input-field {
          max-width: 360px;
          width: 100%;
          background-color: #F8FAFC;
          margin: 6px 0;
          height: 48px;
          border-radius: 14px;
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 0 14px;
          position: relative;
          border: 1px solid #E2E8F0;
          transition: all 0.25s ease;
        }

        .rd-input-field:focus-within {
          background-color: #FFFFFF;
          border-color: #365CFF;
          box-shadow: 0 0 0 3px rgba(54, 92, 255, 0.12);
        }

        .rd-input-field input {
          background: none;
          outline: none;
          border: none;
          line-height: 1;
          font-weight: 500;
          font-size: 0.875rem;
          color: #0F172A;
          width: 100%;
        }

        .rd-input-field input::placeholder {
          color: #94A3B8;
          font-weight: 400;
        }

        .rd-btn {
          width: 100%;
          max-width: 360px;
          height: 46px;
          border-radius: 14px;
          font-weight: 700;
          font-size: 0.875rem;
          cursor: pointer;
          transition: all 0.25s ease;
          display: flex;
          align-items: center;
          justify-content: center;
          border: none;
          outline: none;
        }

        .rd-btn-solid {
          background: linear-gradient(135deg, #365CFF 0%, #4F6BFF 100%);
          color: #FFFFFF;
          box-shadow: 0 8px 20px -4px rgba(54, 92, 255, 0.35);
        }

        .rd-btn-solid:hover {
          transform: translateY(-1.5px);
          box-shadow: 0 12px 25px -4px rgba(54, 92, 255, 0.45);
        }

        .rd-panels-container {
          position: absolute;
          height: 100%;
          width: 100%;
          top: 0;
          left: 0;
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          pointer-events: none;
        }

        .rd-panel {
          display: flex;
          flex-direction: column;
          align-items: flex-end;
          justify-content: space-around;
          text-align: center;
          z-index: 7;
        }

        .rd-left-panel {
          padding: 3rem 16% 2rem 10%;
        }

        .rd-right-panel {
          padding: 3rem 10% 2rem 16%;
        }

        .rd-panel-content {
          color: #FFFFFF;
          display: flex;
          flex-direction: column;
          align-items: center;
          transition: transform 1.1s cubic-bezier(0.77, 0, 0.175, 1), opacity 0.6s ease;
        }

        .rd-left-panel .rd-panel-content {
          transform: translateX(0);
          opacity: 1;
          pointer-events: all;
        }

        .rd-right-panel .rd-panel-content {
          transform: translateX(700px);
          opacity: 0;
          pointer-events: none;
        }

        .rd-auth-container.sign-up-mode .rd-left-panel .rd-panel-content {
          transform: translateX(-700px);
          opacity: 0;
          pointer-events: none;
        }

        .rd-auth-container.sign-up-mode .rd-right-panel .rd-panel-content {
          transform: translateX(0);
          opacity: 1;
          pointer-events: all;
        }

        .rd-panel h3 {
          font-weight: 800;
          line-height: 1.15;
          font-size: 1.75rem;
          margin-bottom: 10px;
          letter-spacing: -0.02em;
          color: #FFFFFF;
        }

        .rd-panel p {
          font-size: 0.875rem;
          padding: 0.4rem 0 1.4rem 0;
          line-height: 1.6;
          color: rgba(255, 255, 255, 0.9);
          max-width: 290px;
        }

        .rd-btn-transparent {
          background: rgba(255, 255, 255, 0.15);
          backdrop-filter: blur(10px);
          border: 1.5px solid rgba(255, 255, 255, 0.65);
          color: #FFFFFF;
          max-width: 160px;
          height: 42px;
          border-radius: 12px;
          font-size: 0.825rem;
          font-weight: 700;
          cursor: pointer;
        }

        .rd-btn-transparent:hover {
          background: rgba(255, 255, 255, 0.28);
          border-color: #FFFFFF;
          transform: translateY(-2px);
        }

        /* ── Dynamic Moving Blue Shape (The 60FPS Slide Effect) ── */
        .rd-auth-container:before {
          content: "";
          position: absolute;
          height: 2000px;
          width: 2000px;
          top: -10%;
          right: 48%;
          transform: translateY(-50%);
          background: linear-gradient(-45deg, #2563EB 0%, #365CFF 40%, #6366F1 75%, #7C3AED 100%);
          transition: transform 1.1s cubic-bezier(0.77, 0, 0.175, 1);
          border-radius: 50%;
          z-index: 6;
          box-shadow: 0 0 90px rgba(54, 92, 255, 0.4);
        }

        .rd-auth-container.sign-up-mode:before {
          transform: translate(100%, -50%);
        }

        .rd-social-text {
          padding: 0.6rem 0 0.4rem 0;
          font-size: 0.775rem;
          color: #94A3B8;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }

        .rd-social-media {
          display: flex;
          justify-content: center;
          gap: 12px;
        }

        .rd-social-icon {
          height: 40px;
          width: 40px;
          display: flex;
          justify-content: center;
          align-items: center;
          border: 1px solid #E2E8F0;
          border-radius: 12px;
          background: #F8FAFC;
          transition: all 0.25s ease;
          cursor: pointer;
        }

        .rd-social-icon:hover {
          border-color: #365CFF;
          background: #FFFFFF;
          transform: translateY(-2px);
          box-shadow: 0 4px 12px rgba(54, 92, 255, 0.15);
        }

        @media (max-width: 870px) {
          .rd-auth-container {
            min-height: 800px;
            height: auto;
          }
          .rd-signin-signup {
            width: 100%;
            top: 95%;
            transform: translate(-50%, -100%);
            left: 50% !important;
            transition: 1.1s cubic-bezier(0.77, 0, 0.175, 1);
          }
          .rd-panels-container {
            grid-template-columns: 1fr;
            grid-template-rows: 1fr 2fr 1fr;
          }
          .rd-panel {
            flex-direction: row;
            justify-content: space-around;
            align-items: center;
            padding: 2rem 8%;
            grid-column: 1 / 2;
          }
          .rd-right-panel {
            grid-row: 3 / 4;
          }
          .rd-left-panel {
            grid-row: 1 / 2;
          }
          .rd-panel-content {
            padding-right: 10%;
          }
          .rd-panel h3 {
            font-size: 1.3rem;
          }
          .rd-panel p {
            font-size: 0.75rem;
            padding: 0.3rem 0;
          }
          .rd-btn-transparent {
            width: 120px;
            height: 38px;
            font-size: 0.75rem;
          }
          .rd-auth-container:before {
            width: 1500px;
            height: 1500px;
            transform: translateX(-50%);
            left: 30%;
            bottom: 68%;
            right: initial;
            top: initial;
            transition: 1.2s cubic-bezier(0.77, 0, 0.175, 1);
          }
          .rd-auth-container.sign-up-mode:before {
            transform: translate(-50%, 100%);
            bottom: 32%;
            right: initial;
          }
          .rd-auth-container.sign-up-mode .rd-left-panel .rd-panel-content {
            transform: translateY(-300px);
          }
          .rd-auth-container.sign-up-mode .rd-right-panel .rd-panel-content {
            transform: translateY(0px);
          }
          .rd-right-panel .rd-panel-content {
            transform: translateY(300px);
          }
          .rd-auth-container.sign-up-mode .rd-signin-signup {
            top: 5%;
            transform: translate(-50%, 0);
          }
        }

        @media (max-width: 570px) {
          .rd-form {
            padding: 0 1.25rem;
          }
          .rd-panel-content {
            padding: 0.5rem 1rem;
          }
        }
      `}</style>
    </div>
  );
};

function SocialIcons() {
  return (
    <>
      <button type="button" className="rd-social-icon" title="Continue with Google">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24">
          <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
          <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
          <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
          <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
        </svg>
      </button>
      <button type="button" className="rd-social-icon" title="Continue with GitHub">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="#0F172A">
          <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
        </svg>
      </button>
      <button type="button" className="rd-social-icon" title="Continue with Microsoft">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24">
          <path fill="#F25022" d="M1 1h10v10H1z"/>
          <path fill="#00A4EF" d="M1 13h10v10H1z"/>
          <path fill="#7FBA00" d="M13 1h10v10H13z"/>
          <path fill="#FFB900" d="M13 13h10v10H13z"/>
        </svg>
      </button>
    </>
  );
}

export default AuthSwitch;
