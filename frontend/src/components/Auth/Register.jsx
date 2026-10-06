import React from 'react';
import { AuthSwitch } from './AuthSwitch';

export const Register = ({ onToggleMode, onSuccess }) => {
  return (
    <AuthSwitch
      initialMode="register"
      onToggleMode={onToggleMode}
      onSuccess={onSuccess}
    />
  );
};

export default Register;
