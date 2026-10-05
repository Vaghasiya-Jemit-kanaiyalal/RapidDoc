import React, { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Mail, Lock, User, Eye, EyeOff, UserPlus, ArrowRight, Sparkles, ShieldCheck, Check } from 'lucide-react';
import { motion } from 'framer-motion';
import loadingEffect from '../../assets/laoding_effect.png';

export const Register = ({ onToggleMode, onSuccess }) => {
  const { register } = useAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [valError, setValError] = useState('');
  const [strength, setStrength] = useState(0);

  // Check password strength
  useEffect(() => {
    let score = 0;
    if (!password) {
      setStrength(0);
      return;
    }
    if (password.length >= 6) score += 1;
    if (/[A-Z]/.test(password)) score += 1;
    if (/[0-9]/.test(password)) score += 1;
    if (/[^A-Za-z0-9]/.test(password)) score += 1;
    setStrength(score);
  }, [password]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setValError('');

    if (!name || !email || !password || !confirmPassword) {
      setValError('Please fill in all fields.');
      return;
    }

    if (password.length < 6) {
      setValError('Password must be at least 6 characters long.');
      return;
    }

    if (password !== confirmPassword) {
      setValError('Passwords do not match.');
      return;
    }

    setLoading(true);
    try {
      await register(name, email, password);
      if (onSuccess) {
        onSuccess();
      } else {
        onToggleMode('dashboard');
      }
    } catch (err) {
      setValError(err.message || 'Registration failed. Try using a different email.');
    } finally {
      setLoading(false);
    }
  };

  const getStrengthLabel = () => {
    switch (strength) {
      case 0: return 'Too Weak';
      case 1: return 'Weak';
      case 2: return 'Medium';
      case 3: return 'Strong';
      case 4: return 'Very Strong';
      default: return 'Weak';
    }
  };

  const getStrengthColor = () => {
    switch (strength) {
      case 0: return 'bg-slate-200';
      case 1: return 'bg-red-500';
      case 2: return 'bg-amber-500';
      case 3: return 'bg-emerald-500';
      case 4: return 'bg-emerald-600';
      default: return 'bg-slate-200';
    }
  };

  return (
    <div className="min-h-screen flex flex-col justify-between py-6 px-4 sm:px-6 lg:px-8 bg-gradient-to-br from-slate-50 via-brand-50/25 to-indigo-50/30 relative overflow-hidden font-sans text-ink">
      {/* Ambient background glows */}
      <div className="pointer-events-none absolute inset-0" aria-hidden="true">
        <div className="absolute -top-40 -right-40 w-96 h-96 bg-brand-500/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '2s' }} />
        <div className="absolute inset-0 bg-[radial-gradient(at_20%_20%,rgba(54,92,255,0.04)_0px,transparent_50%),radial-gradient(at_80%_80%,rgba(139,92,246,0.04)_0px,transparent_50%)]" />
      </div>

      {/* Top Navbar */}
      <header className="max-w-7xl mx-auto w-full flex justify-between items-center z-10">
        <button 
          onClick={() => onToggleMode('landing')} 
          title="Go to Home" 
          className="cursor-pointer rounded-2xl transition hover:scale-105 active:scale-95 flex items-center gap-2.5 group"
        >
          <img src={loadingEffect} alt="RapidDoc Logo" className="w-[48px] h-[48px] object-contain transition-transform group-hover:scale-105" />
          <span className="font-extrabold text-ink text-xl tracking-tight">RapidDoc</span>
        </button>
      </header>

      {/* Main Centered Card Container */}
      <main className="w-full flex-grow flex items-center justify-center py-8 z-10">
        <motion.div 
          initial={{ opacity: 0, y: 20, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
          className="max-w-[460px] w-full bg-white/85 backdrop-blur-2xl rounded-[32px] p-8 sm:p-10 shadow-floating border border-white/80 text-center relative"
        >
          {/* Top Floating Badge */}
          <div className="w-16 h-16 mx-auto mb-5 rounded-2xl border border-slate-200/90 bg-transparent flex items-center justify-center p-2.5 relative group transition-colors duration-200 hover:border-brand-300">
            <img 
              src={loadingEffect} 
              alt="RapidDoc Auth" 
              className={`w-full h-full object-contain transition-transform duration-300 group-hover:scale-105 ${loading ? 'animate-pulse' : ''}`} 
            />
          </div>

          {/* Title & Subtitle */}
          <h2 className="text-2xl sm:text-3xl font-extrabold text-ink tracking-tight mb-2">
            Create your account
          </h2>
          <p className="text-xs sm:text-sm text-secondary max-w-xs mx-auto leading-relaxed mb-6">
            Get started with AI-driven document intelligence and editing for free.
          </p>

          {/* Validation Error Banner */}
          {valError && (
            <motion.div 
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-5 p-3.5 bg-red-50 border border-red-200 text-red-700 text-xs rounded-2xl font-semibold text-left flex items-start gap-2"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-red-500 mt-1.5 shrink-0" />
              <span>{valError}</span>
            </motion.div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-3.5 text-left">
            <div>
              <label className="block text-xs font-bold text-ink mb-1">Full Name</label>
              <div className="relative">
                <User className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="John Doe"
                  className="w-full pl-11 pr-4 py-3 bg-white/90 focus:bg-white border border-borderline focus:border-brand-500 focus:ring-4 focus:ring-brand-500/10 rounded-2xl outline-none text-sm text-ink font-medium transition shadow-xs placeholder:text-slate-400"
                  required
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-ink mb-1">Email address</label>
              <div className="relative">
                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  className="w-full pl-11 pr-4 py-3 bg-white/90 focus:bg-white border border-borderline focus:border-brand-500 focus:ring-4 focus:ring-brand-500/10 rounded-2xl outline-none text-sm text-ink font-medium transition shadow-xs placeholder:text-slate-400"
                  required
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-ink mb-1">Password</label>
              <div className="relative">
                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Create strong password"
                  className="w-full pl-11 pr-11 py-3 bg-white/90 focus:bg-white border border-borderline focus:border-brand-500 focus:ring-4 focus:ring-brand-500/10 rounded-2xl outline-none text-sm text-ink font-medium transition shadow-xs placeholder:text-slate-400"
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

            <div>
              <label className="block text-xs font-bold text-ink mb-1">Confirm Password</label>
              <div className="relative">
                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type={showConfirmPassword ? 'text' : 'password'}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Repeat your password"
                  className="w-full pl-11 pr-11 py-3 bg-white/90 focus:bg-white border border-borderline focus:border-brand-500 focus:ring-4 focus:ring-brand-500/10 rounded-2xl outline-none text-sm text-ink font-medium transition shadow-xs placeholder:text-slate-400"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition p-1 cursor-pointer"
                >
                  {showConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Password strength meter */}
            {password && (
              <motion.div 
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                className="pt-1"
              >
                <div className="flex items-center justify-between text-[11px] font-bold text-secondary mb-1">
                  <span>Password Strength</span>
                  <span className={strength >= 3 ? 'text-emerald-600' : strength >= 2 ? 'text-amber-600' : 'text-red-500'}>
                    {getStrengthLabel()}
                  </span>
                </div>
                <div className="grid grid-cols-4 gap-1.5 h-1.5 w-full bg-slate-100 rounded-full overflow-hidden">
                  {[1, 2, 3, 4].map((step) => (
                    <div
                      key={step}
                      className={`h-full transition-all duration-300 rounded-full ${
                        strength >= step ? getStrengthColor() : 'bg-slate-200'
                      }`}
                    />
                  ))}
                </div>
              </motion.div>
            )}

            {/* Primary Gradient CTA Button */}
            <motion.button
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
              type="submit"
              disabled={loading}
              className="w-full py-4 mt-4 bg-gradient-to-r from-brand-600 via-brand-700 to-indigo-700 hover:from-brand-500 hover:to-indigo-600 text-white font-bold rounded-2xl shadow-soft-blue text-sm transition duration-300 disabled:opacity-50 flex items-center justify-center gap-2 cursor-pointer"
            >
              {loading ? (
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Creating account...</span>
                </div>
              ) : (
                <>
                  <span>Create Account</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </motion.button>
          </form>

          {/* Toggle Mode Link */}
          <div className="text-center mt-6 text-xs font-medium text-secondary">
            Already have an account?{' '}
            <button 
              onClick={() => onToggleMode('login')} 
              className="text-brand-600 hover:text-brand-700 font-extrabold cursor-pointer hover:underline transition"
            >
              Sign in
            </button>
          </div>

          {/* Trust badges */}
          <div className="mt-6 pt-5 border-t border-borderline/50 flex items-center justify-center gap-4 text-[11px] text-secondary font-medium">
            <span className="flex items-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" /> 100% Free Trial
            </span>
            <span className="flex items-center gap-1">
              <Check className="w-3.5 h-3.5 text-brand-600" /> No Credit Card Required
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
