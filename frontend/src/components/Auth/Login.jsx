import React from 'react';
import { AuthSwitch } from './AuthSwitch';

export const Login = ({ onToggleMode, onSuccess, notice = '', onNoticeDismiss }) => {
  return (
    <AuthSwitch
      initialMode="login"
      onToggleMode={onToggleMode}
      onSuccess={onSuccess}
      notice={notice}
      onNoticeDismiss={onNoticeDismiss}
    />
  );
};

export default Login;
