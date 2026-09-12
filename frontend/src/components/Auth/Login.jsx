import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Mail, Lock, Eye, EyeOff, LogIn, ArrowRight } from 'lucide-react';
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

  // Background floating typography letters to match the mockup
  const letters = [
    { char: 'a', top: '8%', left: '22%', size: 'text-lg', delay: '0s' },
    { char: 'b', top: '14%', left: '36%', size: 'text-sm', delay: '1s' },
    { char: 'C', top: '12%', left: '27%', size: 'text-2xl', delay: '2s' },
    { char: 'd', top: '10%', left: '67%', size: 'text-base', delay: '1.5s' },
    { char: 'D', top: '5%', left: '56%', size: 'text-3xl', delay: '0.5s' },
    { char: 'E', top: '3%', left: '92%', size: 'text-2xl', delay: '2.5s' },
    { char: 'E', top: '32%', left: '27%', size: 'text-3xl', delay: '1.2s' },
    { char: 'f', top: '11%', left: '50%', size: 'text-xl', delay: '0.8s' },
    { char: 'F', top: '7%', left: '78%', size: 'text-xl', delay: '1.8s' },
    { char: 'G', top: '20%', left: '88%', size: 'text-xl', delay: '2.2s' },
    { char: 'L', top: '44%', left: '7%', size: 'text-xl', delay: '1.1s' },
    { char: 'M', top: '34%', left: '89%', size: 'text-3xl', delay: '0.3s' },
    { char: 'N', top: '58%', left: '5%', size: 'text-2xl', delay: '2.1s' },
    { char: 'R', top: '72%', left: '5%', size: 'text-4xl', delay: '1.4s' },
    { char: 'S', top: '51%', left: '79%', size: 'text-3xl', delay: '0.7s' },
    { char: 'T', top: '64%', left: '13%', size: 'text-3xl', delay: '1.9s' },
    { char: 'W', top: '83%', left: '90%', size: 'text-2xl', delay: '0.9s' },
    { char: 'X', top: '88%', left: '72%', size: 'text-3xl', delay: '2.4s' },
    { char: 'Y', top: '60%', left: '93%', size: 'text-3xl', delay: '1.7s' },
    { char: 'z', top: '94%', left: '95%', size: 'text-xl', delay: '0.4s' }
  ];

  return (
    <div className="min-h-screen flex flex-col justify-between py-6 px-4 sm:px-6 lg:px-8 bg-gradient-to-br from-[#EEF2FF] via-[#E8EEFF] to-[#E0E7FF] relative overflow-hidden font-sans">
      {/* Floating Typographic Watermark Overlay matching the mockup */}
      <div className="absolute inset-0 pointer-events-none select-none overflow-hidden" aria-hidden="true">
        {letters.map((item, idx) => (
          <span
            key={idx}
            className={`absolute ${item.size} font-serif font-semibold text-indigo-900/15 opacity-60 animate-pulse`}
            style={{
              top: item.top,
              left: item.left,
              animationDuration: '4s',
              animationDelay: item.delay
            }}
          >
            {item.char}
          </span>
        ))}
      </div>

      {/* Top Navbar */}
      <header className="max-w-7xl mx-auto w-full flex justify-between items-center z-10">
        <div className="flex items-center gap-3">
          <button 
            onClick={() => onToggleMode('landing')} 
            title="Go to Home" 
            className="cursor-pointer rounded-2xl transition hover:scale-105 active:scale-95 flex items-center gap-2"
          >
            <img src={logo} alt="RapidDoc Logo" className="w-[50px] h-[50px] object-contain" />
            <span className="font-extrabold text-slate-900 text-lg tracking-tight">RapidDoc</span>
          </button>
        </div>
        <button 
          onClick={() => onToggleMode('landing')} 
          className="text-xs font-extrabold text-indigo-600 hover:text-indigo-800 bg-white/80 backdrop-blur-md px-4 py-2 rounded-xl shadow-xs border border-white transition"
        >
          Home
        </button>
      </header>

      {/* Main Centered Card Container */}
      <main className="w-full flex-grow flex items-center justify-center py-10 z-10">
        <div className="max-w-[440px] w-full bg-white rounded-[36px] p-8 sm:p-10 shadow-2xl shadow-indigo-200/50 border border-white/90 text-center relative">
          
          {/* Top Square Icon Badge */}
          <div className="w-14 h-14 mx-auto mb-6 bg-white rounded-2xl shadow-md border border-slate-100 flex items-center justify-center text-slate-800">
            <LogIn className="w-6 h-6 text-slate-800" />
          </div>

          {/* Title & Subtitle */}
          <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight mb-2">
            Sign in with email
          </h2>
          <p className="text-xs sm:text-sm text-slate-500 max-w-xs mx-auto leading-relaxed mb-8">
            Make a better way to bring your docs, and teams together. For free
          </p>

          {/* Validation Error Banner */}
          {valError && (
            <div className="mb-6 p-3.5 bg-red-50 border border-red-200 text-red-700 text-xs rounded-2xl font-semibold text-left">
              {valError}
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4 text-left">
            <div>
              <div className="relative">
                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Email"
                  className="w-full pl-11 pr-4 py-3.5 bg-slate-50/80 focus:bg-white border border-slate-200/80 focus:border-indigo-500 rounded-2xl outline-none text-sm text-slate-800 font-medium transition shadow-2xs placeholder:text-slate-400"
                  required
                />
              </div>
            </div>

            <div>
              <div className="relative">
                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Password"
                  className="w-full pl-11 pr-11 py-3.5 bg-slate-50/80 focus:bg-white border border-slate-200/80 focus:border-indigo-500 rounded-2xl outline-none text-sm text-slate-800 font-medium transition shadow-2xs placeholder:text-slate-400"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Forgot Password Link */}
            <div className="flex justify-end pt-1">
              <a href="#forgot" onClick={(e) => { e.preventDefault(); alert("Password reset functionality: Please contact your system admin or re-register."); }} className="text-xs font-semibold text-indigo-600 hover:underline">
                Forgot password?
              </a>
            </div>

            {/* Primary Dark Navy CTA Button */}
            <button
              type="submit"
              disabled={loading}
              className="w-full py-4 mt-2 bg-[#0D122C] hover:bg-[#182042] text-white font-bold rounded-2xl shadow-lg shadow-indigo-950/20 text-sm transition duration-200 hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50 flex items-center justify-center gap-2 cursor-pointer"
            >
              {loading ? (
                <span>Signing in...</span>
              ) : (
                <>
                  <span>Get Started</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          {/* Toggle Mode Link */}
          <div className="text-center mt-8 text-xs font-medium text-slate-500">
            Don't have an account?{' '}
            <button 
              onClick={() => onToggleMode('register')} 
              className="text-indigo-600 hover:underline font-extrabold cursor-pointer"
            >
              Sign up
            </button>
          </div>

        </div>
      </main>

      {/* Footer */}
      <footer className="max-w-7xl mx-auto w-full flex flex-col sm:flex-row justify-between items-center text-xs text-slate-400 gap-4 mt-4 z-10">
        <span>© 2026 RapidDoc. All rights reserved.</span>
        <div className="flex gap-6 font-semibold">
          <a href="#privacy" className="hover:underline">Privacy Policy</a>
          <a href="#terms" className="hover:underline">Terms of Service</a>
          <a href="#help" className="hover:underline">Help</a>
        </div>
      </footer>
    </div>
  );
};
