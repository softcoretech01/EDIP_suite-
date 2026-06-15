import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  TextField,
  Button,
  Typography,
  Tabs,
  Tab,
  Alert,
  CircularProgress,
  InputAdornment,
  IconButton
} from '@mui/material';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import Visibility from '@mui/icons-material/Visibility';
import VisibilityOff from '@mui/icons-material/VisibilityOff';
import BusinessIcon from '@mui/icons-material/Business';
import EmailIcon from '@mui/icons-material/Email';
import LockIcon from '@mui/icons-material/Lock';
import PersonIcon from '@mui/icons-material/Person';

interface LoginRegisterProps {
  onLoginSuccess: (token: string, refresh: string, user: any) => void;
  apiUrl: string;
}

export const LoginRegister: React.FC<LoginRegisterProps> = ({ onLoginSuccess, apiUrl }) => {
  const [tabIndex, setTabIndex] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Form Fields
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [tenantName, setTenantName] = useState('');

  // Password visibility
  const [showPassword, setShowPassword] = useState(false);

  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setTabIndex(newValue);
    setErrorMsg(null);
    setSuccessMsg(null);
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setErrorMsg('Please fill in all fields.');
      return;
    }

    setIsLoading(true);
    setErrorMsg(null);

    try {
      const response = await fetch(`${apiUrl}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Failed to authenticate.');
      }

      // Fetch user profile info
      const meResponse = await fetch(`${apiUrl}/auth/me`, {
        headers: { 'Authorization': `Bearer ${data.access_token}` }
      });
      const userData = await meResponse.json();

      if (!meResponse.ok) {
        throw new Error('Failed to retrieve user profile.');
      }

      setSuccessMsg('Authentication successful!');
      setTimeout(() => {
        onLoginSuccess(data.access_token, data.refresh_token, userData);
      }, 500);

    } catch (err: any) {
      setErrorMsg(err.message || 'An error occurred during sign in.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password || !fullName) {
      setErrorMsg('Full Name, Email, and Password are required.');
      return;
    }

    setIsLoading(true);
    setErrorMsg(null);

    try {
      const response = await fetch(`${apiUrl}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          password,
          full_name: fullName,
          tenant_name: tenantName || undefined
        })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Registration failed.');
      }

      setSuccessMsg('Registration successful! Please login with your credentials.');
      setTabIndex(0); // Switch to Login tab
      setPassword(''); // Clear password
    } catch (err: any) {
      setErrorMsg(err.message || 'An error occurred during registration.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'radial-gradient(circle at center, #111827 0%, #030712 100%)',
        position: 'relative',
        overflow: 'hidden',
        px: 2,
        '&::before': {
          content: '""',
          position: 'absolute',
          width: '500px',
          height: '500px',
          background: 'radial-gradient(circle, rgba(0, 240, 255, 0.1) 0%, rgba(0, 0, 0, 0) 70%)',
          top: '-150px',
          left: '-100px',
          pointerEvents: 'none',
        },
        '&::after': {
          content: '""',
          position: 'absolute',
          width: '600px',
          height: '600px',
          background: 'radial-gradient(circle, rgba(176, 38, 255, 0.08) 0%, rgba(0, 0, 0, 0) 70%)',
          bottom: '-200px',
          right: '-100px',
          pointerEvents: 'none',
        }
      }}
    >
      <Card
        sx={{
          maxWidth: 480,
          width: '100%',
          backgroundColor: 'rgba(15, 15, 20, 0.65)',
          backdropFilter: 'blur(30px)',
          border: '1px solid rgba(255, 255, 255, 0.12)',
          boxShadow: '0 24px 64px rgba(0, 0, 0, 0.85), inset 0 1px 0 rgba(255, 255, 255, 0.1)',
          borderRadius: 5,
          position: 'relative',
          zIndex: 1
        }}
      >
        <CardContent sx={{ p: 4 }}>
          {/* Logo / Header */}
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', mb: 3 }}>
            <Box
              sx={{
                width: 50,
                height: 50,
                borderRadius: '12px',
                background: 'linear-gradient(135deg, #00F0FF 0%, #B026FF 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                mb: 2,
                boxShadow: '0 0 24px rgba(0, 240, 255, 0.4)'
              }}
            >
              <AutoAwesomeIcon sx={{ color: '#09090b', fontSize: 28 }} />
            </Box>
            <Typography
              variant="h4"
              align="center"
              sx={{
                fontWeight: 800,
                background: 'linear-gradient(45deg, #00F0FF, #B026FF)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                textShadow: '0 0 30px rgba(0, 240, 255, 0.1)',
                mb: 1
              }}
            >
              EDIP Suite
            </Typography>
            <Typography variant="body2" color="text.secondary" align="center">
              Executive Decision Intelligence Platform
            </Typography>
          </Box>

          {/* Toggle Tabs */}
          <Tabs
            value={tabIndex}
            onChange={handleTabChange}
            centered
            sx={{
              mb: 3,
              borderBottom: '1px solid rgba(255,255,255,0.05)',
              '& .MuiTabs-indicator': {
                background: 'linear-gradient(90deg, #00F0FF, #B026FF)',
                height: '3px',
                borderRadius: '3px'
              },
              '& .MuiTab-root': {
                color: 'text.secondary',
                fontWeight: 600,
                fontSize: '0.95rem',
                '&.Mui-selected': {
                  color: 'primary.main',
                }
              }
            }}
          >
            <Tab label="Sign In" />
            <Tab label="Create Account" />
          </Tabs>

          {/* Alerts */}
          {errorMsg && (
            <Alert severity="error" sx={{ mb: 2, borderRadius: 2, bgcolor: 'rgba(239, 68, 68, 0.1)', color: '#EF4444', border: '1px solid rgba(239, 68, 68, 0.2)' }}>
              {errorMsg}
            </Alert>
          )}
          {successMsg && (
            <Alert severity="success" sx={{ mb: 2, borderRadius: 2, bgcolor: 'rgba(16, 185, 129, 0.1)', color: '#10B981', border: '1px solid rgba(16, 185, 129, 0.2)' }}>
              {successMsg}
            </Alert>
          )}

          {/* Form */}
          {tabIndex === 0 ? (
            // LOGIN FORM
            <form onSubmit={handleLogin}>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
                <TextField
                  fullWidth
                  label="Email Address"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={isLoading}
                  slotProps={{
                    input: {
                      startAdornment: (
                        <InputAdornment position="start">
                          <EmailIcon sx={{ color: 'text.secondary', fontSize: 20 }} />
                        </InputAdornment>
                      ),
                    },
                  }}
                  sx={{
                    '& .MuiInputLabel-root': { color: 'text.secondary' },
                    '& .MuiInputLabel-root.Mui-focused': { color: 'rgba(255, 255, 255, 0.8)' },
                    '& .MuiOutlinedInput-root': {
                      borderRadius: 3,
                      backgroundColor: 'rgba(255, 255, 255, 0.02)',
                      '& fieldset': { borderColor: 'rgba(255, 255, 255, 0.15)' },
                      '&:hover fieldset': { borderColor: 'rgba(255, 255, 255, 0.5)' },
                      '&.Mui-focused fieldset': { borderColor: 'rgba(255, 255, 255, 0.5)' }
                    },
                    '& input:-webkit-autofill': {
                      WebkitBoxShadow: '0 0 0 100px #111827 inset !important',
                      WebkitTextFillColor: '#fff !important',
                      caretColor: '#fff !important',
                      borderRadius: 'inherit'
                    }
                  }}
                />

                <TextField
                  fullWidth
                  label="Password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={isLoading}
                  slotProps={{
                    input: {
                      startAdornment: (
                        <InputAdornment position="start">
                          <LockIcon sx={{ color: 'text.secondary', fontSize: 20 }} />
                        </InputAdornment>
                      ),
                      endAdornment: (
                        <InputAdornment position="end">
                          <IconButton onClick={() => setShowPassword(!showPassword)} edge="end" sx={{ color: 'text.secondary' }}>
                            {showPassword ? <VisibilityOff /> : <Visibility />}
                          </IconButton>
                        </InputAdornment>
                      )
                    },
                  }}
                  sx={{
                    '& .MuiInputLabel-root': { color: 'text.secondary' },
                    '& .MuiInputLabel-root.Mui-focused': { color: 'rgba(255, 255, 255, 0.8)' },
                    '& .MuiOutlinedInput-root': {
                      borderRadius: 3,
                      backgroundColor: 'rgba(255, 255, 255, 0.02)',
                      '& fieldset': { borderColor: 'rgba(255, 255, 255, 0.15)' },
                      '&:hover fieldset': { borderColor: 'rgba(255, 255, 255, 0.5)' },
                      '&.Mui-focused fieldset': { borderColor: 'rgba(255, 255, 255, 0.5)' }
                    },
                    '& input:-webkit-autofill': {
                      WebkitBoxShadow: '0 0 0 100px #111827 inset !important',
                      WebkitTextFillColor: '#fff !important',
                      caretColor: '#fff !important',
                      borderRadius: 'inherit'
                    }
                  }}
                />

                <Button
                  fullWidth
                  type="submit"
                  variant="contained"
                  disabled={isLoading}
                  sx={{
                    mt: 1.5,
                    py: 1.5,
                    borderRadius: 3,
                    background: 'linear-gradient(90deg, #00F0FF 0%, #B026FF 100%)',
                    color: '#09090b',
                    fontSize: '1rem',
                    fontWeight: 700,
                    boxShadow: '0 8px 30px rgba(0, 240, 255, 0.2)',
                    '&:hover': {
                      background: 'linear-gradient(90deg, #80F8FF 0%, #D893FF 100%)',
                      transform: 'translateY(-1px)',
                    }
                  }}
                >
                  {isLoading ? <CircularProgress size={24} color="inherit" /> : 'Access Workspace'}
                </Button>
              </Box>
            </form>
          ) : (
            // REGISTER FORM
            <form onSubmit={handleRegister}>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <TextField
                  fullWidth
                  label="Full Name"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  disabled={isLoading}
                  slotProps={{
                    input: {
                      startAdornment: (
                        <InputAdornment position="start">
                          <PersonIcon sx={{ color: 'text.secondary', fontSize: 20 }} />
                        </InputAdornment>
                      ),
                    },
                  }}
                  sx={{
                    '& .MuiInputLabel-root': { color: 'text.secondary' },
                    '& .MuiInputLabel-root.Mui-focused': { color: 'rgba(255, 255, 255, 0.8)' },
                    '& .MuiOutlinedInput-root': {
                      borderRadius: 3,
                      backgroundColor: 'rgba(255, 255, 255, 0.02)',
                      '& fieldset': { borderColor: 'rgba(255, 255, 255, 0.15)' },
                      '&:hover fieldset': { borderColor: 'rgba(255, 255, 255, 0.5)' },
                      '&.Mui-focused fieldset': { borderColor: 'rgba(255, 255, 255, 0.5)' }
                    },
                    '& input:-webkit-autofill': {
                      WebkitBoxShadow: '0 0 0 100px #111827 inset !important',
                      WebkitTextFillColor: '#fff !important',
                      caretColor: '#fff !important',
                      borderRadius: 'inherit'
                    }
                  }}
                />

                <TextField
                  fullWidth
                  label="Email Address"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={isLoading}
                  slotProps={{
                    input: {
                      startAdornment: (
                        <InputAdornment position="start">
                          <EmailIcon sx={{ color: 'text.secondary', fontSize: 20 }} />
                        </InputAdornment>
                      ),
                    },
                  }}
                  sx={{
                    '& .MuiInputLabel-root': { color: 'text.secondary' },
                    '& .MuiInputLabel-root.Mui-focused': { color: 'rgba(255, 255, 255, 0.8)' },
                    '& .MuiOutlinedInput-root': {
                      borderRadius: 3,
                      backgroundColor: 'rgba(255, 255, 255, 0.02)',
                      '& fieldset': { borderColor: 'rgba(255, 255, 255, 0.15)' },
                      '&:hover fieldset': { borderColor: 'rgba(255, 255, 255, 0.5)' },
                      '&.Mui-focused fieldset': { borderColor: 'rgba(255, 255, 255, 0.5)' }
                    },
                    '& input:-webkit-autofill': {
                      WebkitBoxShadow: '0 0 0 100px #111827 inset !important',
                      WebkitTextFillColor: '#fff !important',
                      caretColor: '#fff !important',
                      borderRadius: 'inherit'
                    }
                  }}
                />

                <TextField
                  fullWidth
                  label="Password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={isLoading}
                  slotProps={{
                    input: {
                      startAdornment: (
                        <InputAdornment position="start">
                          <LockIcon sx={{ color: 'text.secondary', fontSize: 20 }} />
                        </InputAdornment>
                      ),
                      endAdornment: (
                        <InputAdornment position="end">
                          <IconButton onClick={() => setShowPassword(!showPassword)} edge="end" sx={{ color: 'text.secondary' }}>
                            {showPassword ? <VisibilityOff /> : <Visibility />}
                          </IconButton>
                        </InputAdornment>
                      )
                    },
                  }}
                  sx={{
                    '& .MuiInputLabel-root': { color: 'text.secondary' },
                    '& .MuiInputLabel-root.Mui-focused': { color: 'rgba(255, 255, 255, 0.8)' },
                    '& .MuiOutlinedInput-root': {
                      borderRadius: 3,
                      backgroundColor: 'rgba(255, 255, 255, 0.02)',
                      '& fieldset': { borderColor: 'rgba(255, 255, 255, 0.15)' },
                      '&:hover fieldset': { borderColor: 'rgba(255, 255, 255, 0.5)' },
                      '&.Mui-focused fieldset': { borderColor: 'rgba(255, 255, 255, 0.5)' }
                    },
                    '& input:-webkit-autofill': {
                      WebkitBoxShadow: '0 0 0 100px #111827 inset !important',
                      WebkitTextFillColor: '#fff !important',
                      caretColor: '#fff !important',
                      borderRadius: 'inherit'
                    }
                  }}
                />

                <TextField
                  fullWidth
                  label="Organization Name (Optional)"
                  placeholder="e.g. Acme Corp"
                  value={tenantName}
                  onChange={(e) => setTenantName(e.target.value)}
                  disabled={isLoading}
                  slotProps={{
                    input: {
                      startAdornment: (
                        <InputAdornment position="start">
                          <BusinessIcon sx={{ color: 'text.secondary', fontSize: 20 }} />
                        </InputAdornment>
                      ),
                    },
                  }}
                  sx={{
                    '& .MuiInputLabel-root': { color: 'text.secondary' },
                    '& .MuiInputLabel-root.Mui-focused': { color: 'rgba(255, 255, 255, 0.8)' },
                    '& .MuiOutlinedInput-root': {
                      borderRadius: 3,
                      backgroundColor: 'rgba(255, 255, 255, 0.02)',
                      '& fieldset': { borderColor: 'rgba(255, 255, 255, 0.15)' },
                      '&:hover fieldset': { borderColor: 'rgba(255, 255, 255, 0.5)' },
                      '&.Mui-focused fieldset': { borderColor: 'rgba(255, 255, 255, 0.5)' }
                    },
                    '& input:-webkit-autofill': {
                      WebkitBoxShadow: '0 0 0 100px #111827 inset !important',
                      WebkitTextFillColor: '#fff !important',
                      caretColor: '#fff !important',
                      borderRadius: 'inherit'
                    }
                  }}
                />

                <Button
                  fullWidth
                  type="submit"
                  variant="contained"
                  disabled={isLoading}
                  sx={{
                    mt: 1.5,
                    py: 1.5,
                    borderRadius: 3,
                    background: 'linear-gradient(90deg, #00F0FF 0%, #B026FF 100%)',
                    color: '#09090b',
                    fontSize: '1rem',
                    fontWeight: 700,
                    boxShadow: '0 8px 30px rgba(0, 240, 255, 0.2)',
                    '&:hover': {
                      background: 'linear-gradient(90deg, #80F8FF 0%, #D893FF 100%)',
                      transform: 'translateY(-1px)',
                    }
                  }}
                >
                  {isLoading ? <CircularProgress size={24} color="inherit" /> : 'Register Workspace'}
                </Button>
              </Box>
            </form>
          )}
        </CardContent>
      </Card>
    </Box>
  );
};
