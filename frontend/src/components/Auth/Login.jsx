import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Mail, Lock, Eye, EyeOff, LogIn, ArrowRight, Sparkles, CheckCircle2, ShieldCheck } from 'lucide-react';
import { motion } from 'framer-motion';
import logo from '../../assets/logo.png';

export const Login = ({ onToggleMode, onSuccess }) => {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [valError, setValError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setValError('');
    
    if (!email || !password) {
      setValError('Please fill in all fields.');
      return;
    }

    setLoading(true);
    try {
      await login(email, password);
      if (onSuccess) onSuccess();
    } catch (err) {
      setValError(err.message || 'Login failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col justify-between py-6 px-4 sm:px-6 lg:px-8 bg-gradient-to-br from-slate-50 via-brand-50/25 to-indigo-50/30 relative overflow-hidden font-sans text-ink">
      {/* Ambient background glows */}
      <div className="pointer-events-none absolute inset-0" aria-hidden="true">
        <div className="absolute -top-40 -left-40 w-96 h-96 bg-brand-500/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute -bottom-40 -right-40 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '2s' }} />
        <div className="absolute inset-0 bg-[radial-gradient(at_20%_20%,rgba(54,92,255,0.04)_0px,transparent_50%),radial-gradient(at_80%_80%,rgba(139,92,246,0.04)_0px,transparent_50%)]" />
      </div>

      {/* Top Navbar */}
      <header className="max-w-7xl mx-auto w-full flex justify-between items-center z-10">
        <button 
          onClick={() => onToggleMode('landing')} 
          title="Go to Home" 
          className="cursor-pointer rounded-2xl transition hover:scale-105 active:scale-95 flex items-center gap-2.5"
        >
          <img src={logo} alt="RapidDoc Logo" className="w-[52px] h-[52px] object-contain" />
          <span className="font-extrabold text-ink text-xl tracking-tight">RapidDoc</span>
        </button>

        <div className="flex items-center gap-3">
          <button 
            onClick={() => onToggleMode('landing')} 
            className="text-xs font-bold text-secondary hover:text-brand-600 bg-white/80 backdrop-blur-md px-4 py-2 rounded-xl shadow-xs border border-borderline/60 hover:border-brand-200 transition"
          >
            Back to Home
          </button>
        </div>
      </header>

      {/* Main Centered Card Container */}
      <main className="w-full flex-grow flex items-center justify-center py-10 z-10">
        <motion.div 
          initial={{ opacity: 0, y: 20, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
          className="max-w-[440px] w-full bg-white/85 backdrop-blur-2xl rounded-[32px] p-8 sm:p-10 shadow-floating border border-white/80 text-center relative"
        >
          {/* Top Floating Badge */}
          <div className="w-14 h-14 mx-auto mb-6 bg-gradient-to-tr from-brand-600 to-indigo-600 rounded-2xl shadow-soft-blue flex items-center justify-center text-white">
            <LogIn className="w-6 h-6" />
          </div>

          {/* Title & Subtitle */}
          <h2 className="text-2xl sm:text-3xl font-extrabold text-ink tracking-tight mb-2">
            Welcome back
          </h2>
          <p className="text-xs sm:text-sm text-secondary max-w-xs mx-auto leading-relaxed mb-7">
            Sign in to access your documents and continue editing with AI.
          </p>

          {/* Validation Error Banner */}
          {valError && (
            <motion.div 
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-6 p-3.5 bg-red-50 border border-red-200 text-red-700 text-xs rounded-2xl font-semibold text-left flex items-start gap-2"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-red-500 mt-1.5 shrink-0" />
              <span>{valError}</span>
            </motion.div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4 text-left">
            <div>
              <label className="block text-xs font-bold text-ink mb-1.5">Email address</label>
              <div className="relative">
                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  className="w-full pl-11 pr-4 py-3.5 bg-white/90 focus:bg-white border border-borderline focus:border-brand-500 focus:ring-4 focus:ring-brand-500/10 rounded-2xl outline-none text-sm text-ink font-medium transition shadow-xs placeholder:text-slate-400"
                  required
                />
              </div>
            </div>

            <div>
              <div className="flex justify-between items-center mb-1.5">
                <label className="block text-xs font-bold text-ink">Password</label>
                <a 
                  href="#forgot" 
                  onClick={(e) => { e.preventDefault(); alert("Please contact your administrator or re-register to reset credentials."); }} 
                  className="text-xs font-semibold text-brand-600 hover:text-brand-700 transition"
                >
                  Forgot password?
                </a>
              </div>
              <div className="relative">
                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full pl-11 pr-11 py-3.5 bg-white/90 focus:bg-white border border-borderline focus:border-brand-500 focus:ring-4 focus:ring-brand-500/10 rounded-2xl outline-none text-sm text-ink font-medium transition shadow-xs placeholder:text-slate-400"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition p-1 cursor-pointer"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Primary Gradient CTA Button */}
            <motion.button
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
              type="submit"
              disabled={loading}
              className="w-full py-4 mt-3 bg-gradient-to-r from-brand-600 via-brand-700 to-indigo-700 hover:from-brand-500 hover:to-indigo-600 text-white font-bold rounded-2xl shadow-soft-blue text-sm transition duration-300 disabled:opacity-50 flex items-center justify-center gap-2 cursor-pointer"
            >
              {loading ? (
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Signing in...</span>
                </div>
              ) : (
                <>
                  <span>Sign In</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </motion.button>
          </form>

          {/* Toggle Mode Link */}
          <div className="text-center mt-8 text-xs font-medium text-secondary">
            Don't have an account?{' '}
            <button 
              onClick={() => onToggleMode('register')} 
              className="text-brand-600 hover:text-brand-700 font-extrabold cursor-pointer hover:underline transition"
            >
              Create free account
            </button>
          </div>

          {/* Trust badges */}
          <div className="mt-8 pt-6 border-t border-borderline/50 flex items-center justify-center gap-4 text-[11px] text-secondary font-medium">
            <span className="flex items-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" /> End-to-end encrypted
            </span>
            <span className="flex items-center gap-1">
              <Sparkles className="w-3.5 h-3.5 text-purple-500" /> AI-powered editor
            </span>
          </div>

        </motion.div>
      </main>

      {/* Footer */}
      <footer className="max-w-7xl mx-auto w-full flex flex-col sm:flex-row justify-between items-center text-xs text-secondary gap-4 mt-4 z-10">
        <span>© 2026 RapidDoc. All rights reserved.</span>
        <div className="flex gap-6 font-semibold">
          <a href="#privacy" className="hover:text-brand-600 transition">Privacy Policy</a>
          <a href="#terms" className="hover:text-brand-600 transition">Terms of Service</a>
          <a href="#help" className="hover:text-brand-600 transition">Help Center</a>
        </div>
      </footer>
    </div>
  );
};
