"use client";

import { useState, type FormEvent } from "react";

export default function AuthSwitch() {
  const [isSignUp, setIsSignUp] = useState(false);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
  };

  return (
    <div className="auth-switch">
      <style>{`
        .auth-switch,
        .auth-switch * {
          box-sizing: border-box;
        }

        .auth-switch {
          font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #F8FAFC;
          min-height: 100vh;
          width: 100%;
          display: flex;
          justify-content: center;
          align-items: center;
          padding: 20px;
          position: relative;
        }

        .container {
          position: relative;
          width: 100%;
          max-width: 960px;
          height: 610px;
          background: #FFFFFF;
          border-radius: 32px;
          box-shadow: 0 25px 60px -15px rgba(54, 92, 255, 0.20), 0 10px 30px rgba(0, 0, 0, 0.06);
          border: 1px solid rgba(226, 232, 240, 0.95);
          overflow: hidden;
        }

        .forms-container {
          position: absolute;
          width: 100%;
          height: 100%;
          top: 0;
          left: 0;
        }

        .signin-signup {
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

        .container.sign-up-mode .signin-signup {
          left: 25%;
        }

        form {
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

        form.sign-in-form {
          opacity: 1;
          z-index: 2;
          pointer-events: all;
          transform: scale(1);
        }

        form.sign-up-form {
          opacity: 0;
          z-index: 1;
          pointer-events: none;
          transform: scale(0.96);
        }

        .container.sign-up-mode form.sign-in-form {
          opacity: 0;
          z-index: 1;
          pointer-events: none;
          transform: scale(0.96);
        }

        .container.sign-up-mode form.sign-up-form {
          opacity: 1;
          z-index: 2;
          pointer-events: all;
          transform: scale(1);
        }

        .title {
          font-size: 2.2rem;
          color: #0F172A;
          margin-bottom: 6px;
          font-weight: 800;
          letter-spacing: -0.02em;
        }

        .subtitle {
          font-size: 0.875rem;
          color: #64748B;
          margin-bottom: 16px;
          text-align: center;
        }

        .input-field {
          max-width: 360px;
          width: 100%;
          background-color: #F8FAFC;
          margin: 6px 0;
          height: 48px;
          border-radius: 14px;
          display: grid;
          grid-template-columns: 15% 85%;
          padding: 0 0.5rem;
          position: relative;
          border: 1px solid #E2E8F0;
          transition: 0.25s ease;
        }

        .input-field:focus-within {
          background-color: #FFFFFF;
          border-color: #365CFF;
          box-shadow: 0 0 0 3px rgba(54, 92, 255, 0.12);
        }

        .input-field i {
          text-align: center;
          line-height: 48px;
          color: #64748B;
          transition: 0.3s;
          font-size: 1.1rem;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .input-field input {
          background: none;
          outline: none;
          border: none;
          line-height: 1;
          font-weight: 500;
          font-size: 0.9rem;
          color: #0F172A;
          width: 100%;
        }

        .input-field input::placeholder {
          color: #94A3B8;
          font-weight: 400;
        }

        .btn {
          width: 100%;
          max-width: 360px;
          background: linear-gradient(135deg, #365CFF 0%, #4F6BFF 100%);
          border: none;
          outline: none;
          height: 46px;
          border-radius: 14px;
          color: #fff;
          font-weight: 700;
          margin: 12px 0;
          cursor: pointer;
          transition: all 0.25s ease;
          font-size: 0.875rem;
          box-shadow: 0 8px 20px -4px rgba(54, 92, 255, 0.35);
        }

        .btn:hover {
          transform: translateY(-1.5px);
          box-shadow: 0 12px 25px -4px rgba(54, 92, 255, 0.45);
        }

        .panels-container {
          position: absolute;
          height: 100%;
          width: 100%;
          top: 0;
          left: 0;
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          pointer-events: none;
        }

        .panel {
          display: flex;
          flex-direction: column;
          align-items: flex-end;
          justify-content: space-around;
          text-align: center;
          z-index: 7;
        }

        .left-panel {
          padding: 3rem 16% 2rem 10%;
        }

        .right-panel {
          padding: 3rem 10% 2rem 16%;
        }

        .panel .content {
          color: #fff;
          display: flex;
          flex-direction: column;
          align-items: center;
          transition: transform 1.1s cubic-bezier(0.77, 0, 0.175, 1), opacity 0.6s ease;
        }

        .left-panel .content {
          transform: translateX(0);
          opacity: 1;
          pointer-events: all;
        }

        .right-panel .content {
          transform: translateX(700px);
          opacity: 0;
          pointer-events: none;
        }

        .container.sign-up-mode .left-panel .content {
          transform: translateX(-700px);
          opacity: 0;
          pointer-events: none;
        }

        .container.sign-up-mode .right-panel .content {
          transform: translateX(0);
          opacity: 1;
          pointer-events: all;
        }

        .panel h3 {
          font-weight: 800;
          line-height: 1.15;
          font-size: 1.75rem;
          margin-bottom: 10px;
          letter-spacing: -0.02em;
        }

        .panel p {
          font-size: 0.875rem;
          padding: 0.4rem 0 1.4rem 0;
          line-height: 1.6;
          color: rgba(255, 255, 255, 0.9);
          max-width: 290px;
        }

        .btn.transparent {
          margin: 0;
          background: rgba(255, 255, 255, 0.15);
          backdrop-filter: blur(10px);
          border: 1.5px solid rgba(255, 255, 255, 0.65);
          width: 150px;
          height: 42px;
          font-weight: 700;
          font-size: 0.825rem;
          border-radius: 12px;
          box-shadow: none;
          cursor: pointer;
        }

        .btn.transparent:hover {
          background: rgba(255, 255, 255, 0.28);
          border-color: #FFFFFF;
          transform: translateY(-2px);
        }

        /* ── Dynamic Moving Blue Shape (The 60FPS Slide Effect) ── */
        .container:before {
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

        .container.sign-up-mode:before {
          transform: translate(100%, -50%);
        }

        .social-text {
          padding: 0.6rem 0 0.4rem 0;
          font-size: 0.775rem;
          color: #94A3B8;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }

        .social-media {
          display: flex;
          justify-content: center;
          gap: 12px;
        }

        .social-icon {
          height: 40px;
          width: 40px;
          display: flex;
          justify-content: center;
          align-items: center;
          border: 1px solid #E2E8F0;
          border-radius: 12px;
          background: #F8FAFC;
          font-size: 1.1rem;
          transition: all 0.25s ease;
          cursor: pointer;
        }

        .social-icon:hover {
          border-color: #365CFF;
          background: #FFFFFF;
          transform: translateY(-2px);
          box-shadow: 0 4px 12px rgba(54, 92, 255, 0.15);
        }

        @media (max-width: 870px) {
          .container {
            min-height: 800px;
            height: auto;
          }
          .signin-signup {
            width: 100%;
            top: 95%;
            transform: translate(-50%, -100%);
            left: 50% !important;
            transition: 1.1s cubic-bezier(0.77, 0, 0.175, 1);
          }
          .panels-container {
            grid-template-columns: 1fr;
            grid-template-rows: 1fr 2fr 1fr;
          }
          .panel {
            flex-direction: row;
            justify-content: space-around;
            align-items: center;
            padding: 2rem 8%;
            grid-column: 1 / 2;
          }
          .right-panel {
            grid-row: 3 / 4;
          }
          .left-panel {
            grid-row: 1 / 2;
          }
          .panel .content {
            padding-right: 10%;
          }
          .panel h3 {
            font-size: 1.3rem;
          }
          .panel p {
            font-size: 0.75rem;
            padding: 0.3rem 0;
          }
          .btn.transparent {
            width: 120px;
            height: 38px;
            font-size: 0.75rem;
          }
          .container:before {
            width: 1500px;
            height: 1500px;
            transform: translateX(-50%);
            left: 30%;
            bottom: 68%;
            right: initial;
            top: initial;
            transition: 1.2s cubic-bezier(0.77, 0, 0.175, 1);
          }
          .container.sign-up-mode:before {
            transform: translate(-50%, 100%);
            bottom: 32%;
            right: initial;
          }
          .container.sign-up-mode .left-panel .content {
            transform: translateY(-300px);
          }
          .container.sign-up-mode .right-panel .content {
            transform: translateY(0px);
          }
          .right-panel .content {
            transform: translateY(300px);
          }
          .container.sign-up-mode .signin-signup {
            top: 5%;
            transform: translate(-50%, 0);
          }
        }

        @media (max-width: 570px) {
          form {
            padding: 0 1.25rem;
          }
          .panel .content {
            padding: 0.5rem 1rem;
          }
        }
      `}</style>

      <div className={isSignUp ? "container sign-up-mode" : "container"}>
        <div className="forms-container">
          <div className="signin-signup">
            {/* Sign In Form */}
            <form className="sign-in-form" onSubmit={onSubmit}>
              <h2 className="title">Sign In</h2>
              <p className="subtitle">Welcome back! Access your RapidDoc workspace.</p>
              <div className="input-field">
                <i>✉️</i>
                <input type="email" placeholder="Email address" required />
              </div>
              <div className="input-field">
                <i>🔒</i>
                <input type="password" placeholder="Password" required />
              </div>
              <input type="submit" value="Sign In" className="btn solid" />
              <p className="social-text">Or sign in with social platforms</p>
              <div className="social-media">
                <SocialIcons />
              </div>
            </form>

            {/* Sign Up Form */}
            <form className="sign-up-form" onSubmit={onSubmit}>
              <h2 className="title">Sign Up</h2>
              <p className="subtitle">Start generating smart documents with RapidDoc AI.</p>
              <div className="input-field">
                <i>👤</i>
                <input type="text" placeholder="Full name" required />
              </div>
              <div className="input-field">
                <i>✉️</i>
                <input type="email" placeholder="Email address" required />
              </div>
              <div className="input-field">
                <i>🔒</i>
                <input type="password" placeholder="Create password" required />
              </div>
              <input type="submit" value="Get Started" className="btn" />
              <p className="social-text">Or register with social platforms</p>
              <div className="social-media">
                <SocialIcons />
              </div>
            </form>
          </div>
        </div>

        <div className="panels-container">
          <div className="panel left-panel">
            <div className="content">
              <h3>New to RapidDoc?</h3>
              <p>
                Join thousands of teams generating intelligent, professional documentation in seconds.
              </p>
              <button
                type="button"
                className="btn transparent"
                onClick={() => setIsSignUp(true)}
              >
                Sign Up
              </button>
            </div>
          </div>

          <div className="panel right-panel">
            <div className="content">
              <h3>Already Registered?</h3>
              <p>Sign in to continue editing and collaborating on your docs.</p>
              <button
                type="button"
                className="btn transparent"
                onClick={() => setIsSignUp(false)}
              >
                Sign In
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function SocialIcons() {
  return (
    <>
      <a href="#" className="social-icon" title="Continue with Google">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
          <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
          <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
          <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
          <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
        </svg>
      </a>
      <a href="#" className="social-icon" title="Continue with GitHub">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="#0F172A">
          <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
        </svg>
      </a>
      <a href="#" className="social-icon" title="Continue with Microsoft">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24">
          <path fill="#F25022" d="M1 1h10v10H1z"/>
          <path fill="#00A4EF" d="M1 13h10v10H1z"/>
          <path fill="#7FBA00" d="M13 1h10v10H13z"/>
          <path fill="#FFB900" d="M13 13h10v10H13z"/>
        </svg>
      </a>
    </>
  );
}
