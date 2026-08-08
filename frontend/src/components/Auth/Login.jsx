import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Mail, Lock, Eye, EyeOff, ShieldCheck, Sparkles, Zap, ArrowRight } from 'lucide-react';
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

    setLoading(false);
    try {
      setLoading(true);
      await login(email, password);
      if (onSuccess) onSuccess();
    } catch (err) {
      setValError(err.message || 'Login failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col justify-between py-6 px-4 sm:px-6 lg:px-8 bg-slate-50 relative overflow-hidden">
      {/* Background Graphic elements */}
      <div className="absolute top-0 right-0 w-[50%] h-[100%] bg-blue-100/30 rounded-bl-[100px] transform rotate-12 -z-10 blur-xl"></div>
      
      {/* Top Navbar */}
      <header className="max-w-7xl mx-auto w-full flex justify-between items-center z-10">
        <div className="flex items-center">
          <button onClick={() => onToggleMode('landing')} title="Go to Home" className="cursor-pointer rounded-2xl transition hover:scale-105 active:scale-95">
            <img src={logo} alt="RapidDoc Logo" className="w-[80px] h-[80px] object-contain" />
          </button>
        </div>
        <button onClick={() => onToggleMode('landing')} className="text-sm font-semibold text-blue-600 hover:text-blue-700 transition">
          Home
        </button>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto w-full flex-grow flex flex-col lg:flex-row items-center justify-center gap-12 lg:gap-24 my-8 z-10">
        {/* Left Side Hero Information */}
        <div className="w-full lg:w-1/2 flex flex-col justify-center text-left">
          <h1 className="text-4xl sm:text-5xl font-extrabold text-slate-900 tracking-tight mb-4">
            Welcome Back!
          </h1>
          <p className="text-lg text-slate-600 mb-8 max-w-md">
            Sign in to continue your journey with AI-powered document intelligence.
          </p>

          <div className="space-y-6 max-w-md">
            <div className="flex items-start gap-4">
              <div className="p-3 bg-blue-50 text-blue-600 rounded-2xl shadow-sm border border-blue-100">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-bold text-slate-800">Secure & Private</h3>
                <p className="text-sm text-slate-500">Your documents are safe with us.</p>
              </div>
            </div>

            <div className="flex items-start gap-4">
              <div className="p-3 bg-blue-50 text-blue-600 rounded-2xl shadow-sm border border-blue-100">
                <Sparkles className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-bold text-slate-800">AI-Powered</h3>
                <p className="text-sm text-slate-500">Summarize, translate, and understand instantly.</p>
              </div>
            </div>

            <div className="flex items-start gap-4">
              <div className="p-3 bg-blue-50 text-blue-600 rounded-2xl shadow-sm border border-blue-100">
                <Zap className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-bold text-slate-800">All-in-One Platform</h3>
                <p className="text-sm text-slate-500">Edit, analyze, and export without leaving the app.</p>
              </div>
            </div>
          </div>

          {/* Floating Illustration Card */}
          <div className="mt-12 hidden lg:flex items-center justify-start">
            <div className="glass p-6 rounded-3xl shadow-xl w-64 border border-white/50 animate-float flex flex-col gap-4 relative">
              <div className="flex justify-between items-center">
                <div className="w-10 h-2 bg-blue-200 rounded-full"></div>
                <span className="text-[10px] px-2 py-0.5 bg-blue-600 text-white font-semibold rounded-full">AI</span>
              </div>
              <div className="space-y-2">
                <div className="w-full h-2 bg-slate-100 rounded-full"></div>
                <div className="w-[80%] h-2 bg-slate-100 rounded-full"></div>
                <div className="w-[90%] h-2 bg-slate-100 rounded-full"></div>
              </div>
              <div className="absolute -bottom-6 -right-6 w-16 h-16 opacity-30">
                <img src="/laoding_effect.png" alt="Effect" className="w-full h-full animate-spin" style={{ animationDuration: '8s' }} onError={(e) => { e.target.style.display = 'none'; }} />
              </div>
            </div>
          </div>
        </div>

        {/* Right Side Login Form */}
        <div className="w-full lg:w-[460px]">
          <div className="glass p-8 sm:p-10 rounded-[32px] shadow-2xl border border-white/60">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold text-slate-900">Sign in to <span className="text-blue-600">RapidDoc</span></h2>
              <p className="text-sm text-slate-500 mt-1">Enter your credentials to access your account</p>
            </div>

            {valError && (
              <div className="mb-6 p-4 bg-red-50 border border-red-200 text-red-700 text-sm rounded-2xl">
                {valError}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-6">
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Email address</label>
                <div className="relative">
                  <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Enter your email"
                    className="w-full pl-12 pr-4 py-3.5 bg-slate-50/50 focus:bg-white border border-slate-200 focus:border-blue-500 rounded-2xl outline-none transition text-sm text-slate-800"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Password</label>
                <div className="relative">
                  <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter your password"
                    className="w-full pl-12 pr-12 py-3.5 bg-slate-50/50 focus:bg-white border border-slate-200 focus:border-blue-500 rounded-2xl outline-none transition text-sm text-slate-800"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition"
                  >
                    {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
              </div>

              <div className="flex justify-between items-center text-sm">
                <label className="flex items-center gap-2 text-slate-600 cursor-pointer">
                  <input type="checkbox" className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500" />
                  <span>Remember me</span>
                </label>
                <a href="#forgot" className="text-blue-600 hover:underline">Forgot Password?</a>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-4 bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-700 hover:to-blue-600 text-white font-bold rounded-2xl shadow-lg shadow-blue-500/20 flex items-center justify-center gap-2 hover:scale-[1.01] active:scale-[0.99] transition duration-200 disabled:opacity-50"
              >
                {loading ? 'Signing in...' : (
                  <>
                    <span>Sign In</span>
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </form>

            <div className="relative my-8">
              <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-slate-200"></div></div>
              <div className="relative flex justify-center text-xs uppercase"><span className="bg-white/80 px-3 text-slate-400 font-semibold tracking-wider">or continue with</span></div>
            </div>

            <button className="w-full py-3.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 font-semibold rounded-2xl flex items-center justify-center gap-3 transition">
              <img src="https://docs.material-tailwind.com/icons/google.svg" alt="Google logo" className="w-5 h-5" />
              <span>Continue with Google</span>
            </button>

            <div className="text-center mt-8 text-sm text-slate-500">
              Don't have an account?{' '}
              <button onClick={() => onToggleMode('register')} className="text-blue-600 hover:underline font-bold">
                Sign up
              </button>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="max-w-7xl mx-auto w-full flex flex-col sm:flex-row justify-between items-center text-xs text-slate-400 gap-4 mt-8 pt-4 border-t border-slate-200/50">
        <span>© 2026 RapidDoc. All rights reserved.</span>
        <div className="flex gap-6">
          <a href="#privacy" className="hover:underline">Privacy Policy</a>
          <a href="#terms" className="hover:underline">Terms of Service</a>
          <a href="#help" className="hover:underline">Help</a>
        </div>
      </footer>
    </div>
  );
};
