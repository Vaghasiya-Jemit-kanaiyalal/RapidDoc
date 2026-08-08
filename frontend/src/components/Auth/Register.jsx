import React, { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Mail, Lock, User, Eye, EyeOff, FileEdit, Sparkles, Download, ArrowRight } from 'lucide-react';
import logo from '../../assets/logo.png';

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
  const [strength, setStrength] = useState(0); // 0 to 4

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
      // Automatically toggle to login mode after successful signup
      onToggleMode('login');
    } catch (err) {
      setValError(err.message || 'Registration failed. Try using a different email.');
    } finally {
      setLoading(false);
    }
  };

  const getStrengthLabel = () => {
    switch (strength) {
      case 0: return 'Weak';
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
      case 2: return 'bg-orange-400';
      case 3: return 'bg-green-500';
      case 4: return 'bg-emerald-600';
      default: return 'bg-slate-200';
    }
  };

  return (
    <div className="min-h-screen flex flex-col justify-between py-6 px-4 sm:px-6 lg:px-8 bg-slate-50 relative overflow-hidden">
      {/* Background Graphic elements */}
      <div className="absolute top-0 left-0 w-[50%] h-[100%] bg-blue-100/30 rounded-br-[100px] transform -rotate-12 -z-10 blur-xl"></div>
      
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
      <main className="max-w-7xl mx-auto w-full flex-grow flex flex-col-reverse lg:flex-row items-center justify-center gap-12 lg:gap-24 my-8 z-10">
        {/* Left Side Sign-Up Form */}
        <div className="w-full lg:w-[460px]">
          <div className="glass p-8 sm:p-10 rounded-[32px] shadow-2xl border border-white/60">
            <div className="text-center mb-6">
              <h2 className="text-2xl font-bold text-slate-900">Create Your <span className="text-blue-600">Account</span></h2>
              <p className="text-sm text-slate-500 mt-1">Join RapidDoc and transform the way you work with documents</p>
            </div>

            {valError && (
              <div className="mb-6 p-4 bg-red-50 border border-red-200 text-red-700 text-sm rounded-2xl">
                {valError}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Full Name</label>
                <div className="relative">
                  <User className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Enter your full name"
                    className="w-full pl-12 pr-4 py-3 bg-slate-50/50 focus:bg-white border border-slate-200 focus:border-blue-500 rounded-2xl outline-none transition text-sm text-slate-800"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Email address</label>
                <div className="relative">
                  <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Enter your email"
                    className="w-full pl-12 pr-4 py-3 bg-slate-50/50 focus:bg-white border border-slate-200 focus:border-blue-500 rounded-2xl outline-none transition text-sm text-slate-800"
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
                    placeholder="Create a password"
                    className="w-full pl-12 pr-12 py-3 bg-slate-50/50 focus:bg-white border border-slate-200 focus:border-blue-500 rounded-2xl outline-none transition text-sm text-slate-800"
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

              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Confirm Password</label>
                <div className="relative">
                  <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                  <input
                    type={showConfirmPassword ? 'text' : 'password'}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Confirm your password"
                    className="w-full pl-12 pr-12 py-3 bg-slate-50/50 focus:bg-white border border-slate-200 focus:border-blue-500 rounded-2xl outline-none transition text-sm text-slate-800"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition"
                  >
                    {showConfirmPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
              </div>

              {/* Password strength meter */}
              {password && (
                <div className="space-y-1 pt-1">
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-slate-500">Password strength</span>
                    <span className="font-semibold text-slate-700">{getStrengthLabel()}</span>
                  </div>
                  <div className="grid grid-cols-4 gap-1.5 h-1.5">
                    <div className={`rounded-full transition duration-300 ${strength >= 1 ? getStrengthColor() : 'bg-slate-200'}`}></div>
                    <div className={`rounded-full transition duration-300 ${strength >= 2 ? getStrengthColor() : 'bg-slate-200'}`}></div>
                    <div className={`rounded-full transition duration-300 ${strength >= 3 ? getStrengthColor() : 'bg-slate-200'}`}></div>
                    <div className={`rounded-full transition duration-300 ${strength >= 4 ? getStrengthColor() : 'bg-slate-200'}`}></div>
                  </div>
                </div>
              )}

              <label className="flex items-start gap-2.5 text-xs text-slate-500 py-2 cursor-pointer">
                <input type="checkbox" required className="w-4 h-4 mt-0.5 rounded border-slate-300 text-blue-600 focus:ring-blue-500" />
                <span>
                  I agree to the <a href="#terms" className="text-blue-600 hover:underline">Terms of Service</a> and <a href="#privacy" className="text-blue-600 hover:underline">Privacy Policy</a>
                </span>
              </label>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3.5 bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-700 hover:to-blue-600 text-white font-bold rounded-2xl shadow-lg shadow-blue-500/20 flex items-center justify-center gap-2 hover:scale-[1.01] active:scale-[0.99] transition duration-200 disabled:opacity-50"
              >
                {loading ? 'Creating Account...' : (
                  <>
                    <span>Create Account</span>
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </form>

            <div className="relative my-6">
              <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-slate-200"></div></div>
              <div className="relative flex justify-center text-xs uppercase"><span className="bg-white/80 px-3 text-slate-400 font-semibold tracking-wider">or sign up with</span></div>
            </div>

            <button className="w-full py-3 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 font-semibold rounded-2xl flex items-center justify-center gap-3 transition">
              <img src="https://docs.material-tailwind.com/icons/google.svg" alt="Google logo" className="w-5 h-5" />
              <span>Continue with Google</span>
            </button>

            <div className="text-center mt-6 text-sm text-slate-500">
              Already have an account?{' '}
              <button onClick={() => onToggleMode('login')} className="text-blue-600 hover:underline font-bold">
                Sign in
              </button>
            </div>
          </div>
        </div>

        {/* Right Side Info Features */}
        <div className="w-full lg:w-1/2 flex flex-col justify-center text-left">
          <h2 className="text-3xl font-extrabold text-slate-900 mb-2">Create Your Account</h2>
          <p className="text-lg text-slate-600 mb-10 max-w-md">
            Join RapidDoc and transform the way you work with documents.
          </p>

          <div className="space-y-8 max-w-md">
            <div className="flex items-start gap-4">
              <div className="p-3 bg-blue-50 text-blue-600 rounded-2xl border border-blue-100 shadow-sm">
                <FileEdit className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-bold text-slate-800">Smart Document Editing</h3>
                <p className="text-sm text-slate-500">Edit documents with AI assistance and smart suggestions.</p>
              </div>
            </div>

            <div className="flex items-start gap-4">
              <div className="p-3 bg-blue-50 text-blue-600 rounded-2xl border border-blue-100 shadow-sm">
                <Sparkles className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-bold text-slate-800">Multiple AI Tools</h3>
                <p className="text-sm text-slate-500">Summarize, translate, generate MCQs, notes, flashcards and more.</p>
              </div>
            </div>

            <div className="flex items-start gap-4">
              <div className="p-3 bg-blue-50 text-blue-600 rounded-2xl border border-blue-100 shadow-sm">
                <Download className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-bold text-slate-800">Export Anywhere</h3>
                <p className="text-sm text-slate-500">Download your documents in DOCX, PDF and other formats.</p>
              </div>
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
