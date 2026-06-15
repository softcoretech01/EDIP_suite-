import React, { useState, useEffect, useRef } from 'react';
import { ThemeProvider, CssBaseline, Box, Typography, Drawer, List, ListItem, ListItemButton, ListItemIcon, ListItemText, Container, Paper, Avatar, IconButton } from '@mui/material';
import axios from 'axios';
import { darkTheme } from './theme';
import { AIChat } from './components/Chat/AIChat';
import { DynamicDashboard } from './components/Dashboard/DynamicDashboard';
import StorageIcon from '@mui/icons-material/Storage';
import AddBoxIcon from '@mui/icons-material/AddBox';
import DashboardIcon from '@mui/icons-material/Dashboard';
import PersonIcon from '@mui/icons-material/Person';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import EditIcon from '@mui/icons-material/Edit';
import { Select, MenuItem, FormControl, InputLabel, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, CircularProgress, Button } from '@mui/material';
import { LoginRegister } from './components/Auth/LoginRegister';

const DRAWER_WIDTH = 260;
const API_URL = 'http://localhost:8000';

interface ChatMessage {
  id: string;
  role: 'user' | 'ai';
  text: string;
  dashboardData?: any;
}

interface ChatHistoryMessage {
  id: number;
  question: string;
  response_json: any;
  created_at: string;
}

interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  messages: ChatHistoryMessage[];
}

function App() {
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'));
  const [user, setUser] = useState<any | null>(null);
  const [isCheckingAuth, setIsCheckingAuth] = useState<boolean>(true);

  const [isLoading, setIsLoading] = useState(false);
  const [isDashboardLoading, setIsDashboardLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [recents, setRecents] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string>(() => crypto.randomUUID());
  const messagesEndRef = useRef<null | HTMLDivElement>(null);
  const [connections, setConnections] = useState<any[]>([]);
  const [selectedConnectionId, setSelectedConnectionId] = useState<number>(0);
  const [viewMode, setViewMode] = useState<'chat' | 'dashboard'>('chat');
  const [dashboardSearch, setDashboardSearch] = useState('');
  const [dashboardData, setDashboardData] = useState<any | null>(null);
  const [chatInput, setChatInput] = useState('');

  const handleEditMessage = (index: number, text: string) => {
    setMessages(prev => prev.slice(0, index));
    setChatInput(text);
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('refreshToken');
    delete axios.defaults.headers.common['Authorization'];
    setUser(null);
    setToken(null);
    setMessages([]);
    setRecents([]);
  };

  const handleLoginSuccess = (accessToken: string, refreshToken: string, userData: any) => {
    localStorage.setItem('token', accessToken);
    localStorage.setItem('refreshToken', refreshToken);
    axios.defaults.headers.common['Authorization'] = `Bearer ${accessToken}`;
    setToken(accessToken);
    setUser(userData);
  };

  // Setup request/response interceptors for automatic token refresh
  useEffect(() => {
    const requestInterceptor = axios.interceptors.request.use(
      (config) => {
        const t = localStorage.getItem('token');
        if (t) {
          config.headers['Authorization'] = `Bearer ${t}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    const responseInterceptor = axios.interceptors.response.use(
      (response) => response,
      async (error) => {
        const originalRequest = error.config;
        if (error.response?.status === 401 && !originalRequest._retry) {
          originalRequest._retry = true;
          const rt = localStorage.getItem('refreshToken');
          if (rt) {
            try {
              const res = await axios.post(`${API_URL}/auth/refresh`, { refresh_token: rt });
              const newAccessToken = res.data.access_token;
              localStorage.setItem('token', newAccessToken);
              axios.defaults.headers.common['Authorization'] = `Bearer ${newAccessToken}`;
              originalRequest.headers['Authorization'] = `Bearer ${newAccessToken}`;
              return axios(originalRequest);
            } catch (refreshError) {
              console.error("Refresh token expired or invalid", refreshError);
              handleLogout();
            }
          } else {
            handleLogout();
          }
        }
        return Promise.reject(error);
      }
    );

    return () => {
      axios.interceptors.request.eject(requestInterceptor);
      axios.interceptors.response.eject(responseInterceptor);
    };
  }, []);

  // Check initial authentication state
  useEffect(() => {
    const initializeAuth = async () => {
      const storedToken = localStorage.getItem('token');
      const storedRefresh = localStorage.getItem('refreshToken');
      
      if (storedToken) {
        axios.defaults.headers.common['Authorization'] = `Bearer ${storedToken}`;
        try {
          const res = await axios.get(`${API_URL}/auth/me`);
          setUser(res.data);
        } catch (e: any) {
          console.warn("Access token validation failed on load, trying refresh...", e);
          if (storedRefresh) {
            try {
              const refreshRes = await axios.post(`${API_URL}/auth/refresh`, { refresh_token: storedRefresh });
              const newAccessToken = refreshRes.data.access_token;
              localStorage.setItem('token', newAccessToken);
              axios.defaults.headers.common['Authorization'] = `Bearer ${newAccessToken}`;
              
              const meRes = await axios.get(`${API_URL}/auth/me`);
              setUser(meRes.data);
              setToken(newAccessToken);
            } catch (refreshErr) {
              console.error("Auto refresh failed", refreshErr);
              handleLogout();
            }
          } else {
            handleLogout();
          }
        }
      }
      setIsCheckingAuth(false);
    };

    initializeAuth();
  }, []);

  const fetchHistory = async () => {
    try {
      const res = await axios.get(`${API_URL}/chat/history`);
      setRecents(res.data);
    } catch (e) {
      console.error("Failed to load chat history", e);
    }
  };

  useEffect(() => {
    if (user) {
      axios.get(`${API_URL}/erp/connections`).then(res => {
        setConnections(res.data);
        if (res.data.length > 0) {
          setSelectedConnectionId(res.data[res.data.length - 1].id);
        }
      }).catch(console.error);

      fetchHistory();
    }
  }, [user]);

  const handleAsk = async (question: string) => {
    if (!selectedConnectionId || selectedConnectionId === 0) {
      const aiErrorMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'ai',
        text: 'Error: No ERP connection available. Please set up a connection first.',
        dashboardData: { error: 'No ERP connection available.' }
      };
      setMessages(prev => [...prev, aiErrorMsg]);
      return;
    }
    const userMsg: ChatMessage = { id: Date.now().toString(), role: 'user', text: question };
    setMessages(prev => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const response = await axios.post(`${API_URL}/chat/ask`, {
        connection_id: selectedConnectionId,
        question: question,
        session_id: currentSessionId
      });

      const aiMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'ai',
        text: response.data.error ? `Error: ${response.data.error}` : (response.data.summary || "Here is the data you requested:"),
        dashboardData: response.data
      };
      setMessages(prev => [...prev, aiMsg]);

    } catch (error: any) {
      console.error(error);
      const errorText = error.response?.data?.detail || "Unable to retrieve information.";
      const aiErrorMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'ai',
        text: `Error: ${errorText}`,
        dashboardData: { error: errorText }
      };
      setMessages(prev => [...prev, aiErrorMsg]);
    } finally {
      setIsLoading(false);
      fetchHistory();
    }
  };

  const handleDashboardAsk = async (question: string) => {
    if (!selectedConnectionId || selectedConnectionId === 0) {
      setDashboardData({ error: 'No ERP connection available. Please set up a connection first.' });
      return;
    }
    setIsDashboardLoading(true);
    try {
      const response = await axios.post(`${API_URL}/chat/ask`, {
        connection_id: selectedConnectionId,
        question: question,
        view_mode: 'dashboard'
      });
      setDashboardData(response.data);
    } catch (error: any) {
      console.error(error);
      setDashboardData({ error: error.response?.data?.detail || "Unable to retrieve information." });
    } finally {
      setIsDashboardLoading(false);
    }
  };

  const resetChat = () => {
    setMessages([]);
    setCurrentSessionId(crypto.randomUUID());
    setViewMode('chat');
  };

  const loadHistorySession = (session: ChatSession) => {
    setViewMode('chat');
    setCurrentSessionId(session.id);

    const loadedMessages: ChatMessage[] = [];
    session.messages.forEach((msg) => {
      loadedMessages.push({ id: `user-${msg.id}`, role: 'user', text: msg.question });
      loadedMessages.push({
        id: `ai-${msg.id}`,
        role: 'ai',
        text: msg.response_json.summary || "Here is the data you requested:",
        dashboardData: msg.response_json
      });
    });
    setMessages(loadedMessages);
  };

  const renderSimpleTable = (data: any[], fullDashboardData?: any) => {
    if (!data || data.length === 0) return null;
    const keys = Object.keys(data[0]);
    return (
      <TableContainer component={Paper} sx={{ mt: 2, bgcolor: 'background.paper', borderRadius: 2, overflow: 'hidden', border: '1px solid rgba(255,255,255,0.05)' }}>
        <Table size="small">
          <TableHead sx={{ bgcolor: 'rgba(255,255,255,0.02)' }}>
            <TableRow>
              {keys.map(k => (
                <TableCell key={k} sx={{ color: 'text.secondary', fontWeight: 600 }}>{k}</TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {data.slice(0, 10).map((row, i) => (
              <TableRow key={i} sx={{ '&:last-child td, &:last-child th': { border: 0 } }}>
                {keys.map(k => (
                  <TableCell key={k} sx={{ color: 'text.primary' }}>{row[k]}</TableCell>
                ))}
              </TableRow>
            ))}
            {data.length > 10 && (
              <TableRow>
                <TableCell colSpan={keys.length} align="center" sx={{ py: 1 }}>
                  <Button 
                    variant="text" 
                    size="small" 
                    onClick={() => {
                       if (fullDashboardData) {
                         setDashboardData(fullDashboardData);
                         setViewMode('dashboard');
                       }
                    }}
                    sx={{ textTransform: 'none', color: 'primary.main' }}
                  >
                    ... and {data.length - 10} more rows (Click to view full data in Dashboard)
                  </Button>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    );
  };

  if (isCheckingAuth) {
    return (
      <ThemeProvider theme={darkTheme}>
        <CssBaseline />
        <Box sx={{ display: 'flex', height: '100vh', alignItems: 'center', justifyContent: 'center', bgcolor: '#09090b' }}>
          <CircularProgress size={40} color="primary" />
        </Box>
      </ThemeProvider>
    );
  }

  if (!user) {
    return (
      <ThemeProvider theme={darkTheme}>
        <CssBaseline />
        <LoginRegister apiUrl={API_URL} onLoginSuccess={handleLoginSuccess} />
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider theme={darkTheme}>
      <CssBaseline />
      <Box sx={{ display: 'flex', height: '100vh', overflow: 'hidden', bgcolor: 'background.default' }}>

        {/* Sidebar */}
        <Drawer
          variant="permanent"
          sx={{
            width: DRAWER_WIDTH,
            flexShrink: 0,
            [`& .MuiDrawer-paper`]: {
              width: DRAWER_WIDTH,
              boxSizing: 'border-box',
              backgroundColor: 'rgba(9, 9, 11, 0.8)',
              backdropFilter: 'blur(20px)',
              borderRight: '1px solid rgba(255,255,255,0.05)',
              overflowX: 'hidden'
            },
          }}
        >
          <Box sx={{ p: 3, display: 'flex', flexDirection: 'column', height: '100%' }}>
            <Box sx={{ flexGrow: 1, overflowY: 'auto', pr: 0.5 }}>
              <Typography variant="h5" sx={{
                fontWeight: 800,
                mb: 4,
                display: 'flex',
                alignItems: 'center',
                background: 'linear-gradient(45deg, #00F0FF, #B026FF)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                textShadow: '0 0 20px rgba(0, 240, 255, 0.3)'
              }}>
                <AutoAwesomeIcon sx={{ mr: 1.5, color: '#00F0FF', WebkitTextFillColor: 'initial' }} /> EDIP Suite
              </Typography>

              {connections.length > 0 && (
                <FormControl fullWidth size="small" sx={{ mb: 3 }}>
                  <InputLabel sx={{ color: '#9CA3AF' }}>Database</InputLabel>
                  <Select
                    value={selectedConnectionId}
                    label="Database"
                    onChange={(e) => setSelectedConnectionId(Number(e.target.value))}
                    sx={{ color: 'white', '.MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.2)' } }}
                  >
                    {connections.map((conn) => (
                      <MenuItem key={conn.id} value={conn.id}>
                        {conn.name}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              )}

              <List sx={{ pt: 0 }}>
                <ListItem disablePadding>
                  <ListItemButton onClick={resetChat} sx={{ borderRadius: 2, mb: 0.5, bgcolor: viewMode === 'chat' ? 'rgba(255,255,255,0.1)' : 'transparent' }}>
                    <ListItemIcon sx={{ minWidth: 40 }}><AddBoxIcon sx={{ color: viewMode === 'chat' ? 'primary.main' : '#E5E7EB', fontSize: 20 }} /></ListItemIcon>
                    <ListItemText primary={<Typography sx={{ color: viewMode === 'chat' ? 'primary.main' : '#E5E7EB', fontSize: '0.95rem' }}>New chat</Typography>} />
                  </ListItemButton>
                </ListItem>
                <ListItem disablePadding>
                  <ListItemButton onClick={() => setViewMode('dashboard')} sx={{ borderRadius: 2, mb: 0.5, bgcolor: viewMode === 'dashboard' ? 'rgba(255,255,255,0.1)' : 'transparent' }}>
                    <ListItemIcon sx={{ minWidth: 40 }}><DashboardIcon sx={{ color: viewMode === 'dashboard' ? 'primary.main' : '#E5E7EB', fontSize: 20 }} /></ListItemIcon>
                    <ListItemText primary={<Typography sx={{ color: viewMode === 'dashboard' ? 'primary.main' : '#E5E7EB', fontSize: '0.95rem' }}>Dashboard</Typography>} />
                  </ListItemButton>
                </ListItem>
              </List>

              {recents.length > 0 && (
                <>
                  <Typography variant="subtitle2" sx={{ color: '#F9FAFB', mt: 3, mb: 1, px: 2, fontWeight: 700, fontSize: '0.85rem' }}>
                    Recents
                  </Typography>
                  <List>
                    {recents.map((session) => (
                      <ListItem key={session.id} disablePadding>
                        <ListItemButton
                          onClick={() => loadHistorySession(session)}
                          sx={{
                            borderRadius: 2,
                            mb: 0.5,
                            py: 0.75,
                            '&:hover': { backgroundColor: '#2A2B32' },
                            bgcolor: currentSessionId === session.id ? 'rgba(255,255,255,0.05)' : 'transparent'
                          }}
                        >
                          <ListItemText
                            primary={
                              <Typography sx={{
                                color: currentSessionId === session.id ? '#00F0FF' : '#D1D5DB',
                                fontSize: '0.85rem',
                                whiteSpace: 'nowrap',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                fontWeight: currentSessionId === session.id ? 600 : 400
                              }}>
                                {session.title}
                              </Typography>
                            }
                          />
                        </ListItemButton>
                      </ListItem>
                    ))}
                  </List>
                </>
              )}
            </Box>

            {/* User details and Logout button */}
            <Box sx={{ borderTop: '1px solid rgba(255,255,255,0.05)', pt: 2, mt: 'auto' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Avatar sx={{ bgcolor: 'secondary.main', width: 36, height: 36, mr: 1.5 }}>
                  {user.full_name ? user.full_name.charAt(0) : user.email.charAt(0).toUpperCase()}
                </Avatar>
                <Box sx={{ overflow: 'hidden' }}>
                  <Typography variant="subtitle2" noWrap sx={{ fontWeight: 600, color: 'text.primary', fontSize: '0.85rem' }}>
                    {user.full_name || 'Business User'}
                  </Typography>
                  <Typography variant="caption" noWrap sx={{ color: 'text.secondary', display: 'block', fontSize: '0.75rem' }}>
                    {user.roles && user.roles.length > 0 ? user.roles[0] : 'User'}
                  </Typography>
                </Box>
              </Box>
              <Button
                fullWidth
                size="small"
                variant="outlined"
                color="inherit"
                onClick={handleLogout}
                sx={{
                  borderColor: 'rgba(255,255,255,0.1)',
                  color: 'text.secondary',
                  borderRadius: 2.5,
                  fontSize: '0.8rem',
                  py: 0.75,
                  '&:hover': {
                    borderColor: 'primary.main',
                    color: 'primary.main',
                    backgroundColor: 'rgba(0, 240, 255, 0.05)'
                  }
                }}
              >
                Sign Out
              </Button>
            </Box>
          </Box>
        </Drawer>

        {/* Main Content Area */}
        <Box component="main" sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', position: 'relative' }}>

          {viewMode === 'dashboard' ? (
            <Box sx={{ flexGrow: 1, overflowY: 'auto', p: 4 }}>
              <Container maxWidth="xl">
                <Typography variant="h4" gutterBottom sx={{ fontWeight: 600, color: 'text.primary', mb: 4 }}>
                  Data Dashboard
                </Typography>
                <Box sx={{ mb: 4 }}>
                  <AIChat 
                    onAsk={handleDashboardAsk} 
                    isLoading={isDashboardLoading} 
                    value={dashboardSearch} 
                    onChange={setDashboardSearch} 
                    clearOnSubmit={false} 
                  />
                </Box>
                {isDashboardLoading && (
                  <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', py: 10 }}>
                    <CircularProgress size={40} sx={{ color: '#00F0FF', mr: 2 }} />
                    <Typography variant="h6" color="text.secondary">Analyzing data and generating dashboard...</Typography>
                  </Box>
                )}

                {dashboardData && !isDashboardLoading && (
                  <DynamicDashboard result={dashboardData} />
                )}

                {!dashboardData && !isDashboardLoading && (
                  <Paper sx={{ p: 10, textAlign: 'center', bgcolor: 'rgba(255,255,255,0.02)', border: '1px dashed rgba(255,255,255,0.1)' }}>
                    <DashboardIcon sx={{ fontSize: 60, color: 'text.secondary', opacity: 0.5, mb: 2 }} />
                    <Typography variant="h6" color="text.secondary">Search your ERP data to generate a dashboard</Typography>
                  </Paper>
                )}
              </Container>
            </Box>
          ) : (
            <>
              {messages.length === 0 ? (
                // Empty State
                <Container maxWidth="md" sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center' }}>
                  <Typography variant="h2" gutterBottom sx={{
                    fontWeight: 800,
                    mb: 2,
                    background: 'linear-gradient(45deg, #F8FAFC, #94A3B8)',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                  }}>
                    EDIP AI Assistant
                  </Typography>
                  <Typography variant="h6" color="text.secondary" sx={{ mb: 6, textAlign: 'center' }}>
                    Ask me questions about your ERP data.
                  </Typography>
                  <Box sx={{ width: '100%' }}>
                    <AIChat onAsk={handleAsk} isLoading={isLoading} value={chatInput} onChange={setChatInput} />
                  </Box>
                </Container>
              ) : (
                // Chat History State
                <Box sx={{ flexGrow: 1, overflowY: 'auto', pb: 15, pt: 4 }}>
                  <Container maxWidth="md">
                    {messages.map((msg, index) => (
                      <Box key={msg.id} sx={{ display: 'flex', mb: 4, justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
                        <Box sx={{ display: 'flex', gap: 2, flexDirection: msg.role === 'user' ? 'row-reverse' : 'row', maxWidth: '80%', alignItems: 'flex-start' }}>
                          <Avatar sx={{ bgcolor: msg.role === 'ai' ? 'primary.main' : 'grey.800' }}>
                            {msg.role === 'ai' ? <AutoAwesomeIcon /> : <PersonIcon />}
                          </Avatar>
                           <Box sx={{ display: 'flex', flexDirection: msg.role === 'user' ? 'row-reverse' : 'row', alignItems: 'center', gap: 1 }}>
                            <Box sx={{
                              p: 2,
                              borderRadius: 2,
                              bgcolor: msg.role === 'user' ? 'primary.dark' : 'background.paper',
                              boxShadow: msg.role === 'ai' ? '0 4px 20px rgba(0,0,0,0.5)' : 'none',
                              border: msg.role === 'ai' ? '1px solid rgba(255,255,255,0.05)' : 'none'
                            }}>
                              <Typography variant="body1" sx={{ color: 'text.primary', whiteSpace: 'pre-wrap', lineHeight: 1.6, fontSize: '0.92rem', textAlign: 'left' }}>
                                {msg.text}
                              </Typography>
                              {msg.role === 'ai' && msg.dashboardData && msg.dashboardData.data && msg.dashboardData.data.length > 0 && (
                                renderSimpleTable(msg.dashboardData.data, msg.dashboardData)
                              )}
                            </Box>
                            {msg.role === 'user' && !isLoading && (
                              <IconButton onClick={() => handleEditMessage(index, msg.text)} size="small" sx={{ color: 'text.secondary', '&:hover': { color: 'primary.main' } }}>
                                <EditIcon fontSize="small" />
                              </IconButton>
                            )}
                          </Box>
                        </Box>
                      </Box>
                    ))}
                    {isLoading && (
                      <Box sx={{ display: 'flex', mb: 4, justifyContent: 'flex-start' }}>
                        <Box sx={{ display: 'flex', gap: 2, flexDirection: 'row', maxWidth: '80%' }}>
                          <Avatar sx={{ bgcolor: 'primary.main' }}>
                            <AutoAwesomeIcon />
                          </Avatar>
                          <Box sx={{
                            p: 2,
                            borderRadius: 2,
                            bgcolor: 'background.paper',
                            boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
                            border: '1px solid rgba(255,255,255,0.05)',
                            display: 'flex',
                            alignItems: 'center'
                          }}>
                            <CircularProgress size={20} color="primary" />
                            <Typography variant="body2" sx={{ ml: 2, color: 'text.secondary', textAlign: 'left' }}>
                              Analyzing data and generating insights...
                            </Typography>
                          </Box>
                        </Box>
                      </Box>
                    )}
                    <div ref={messagesEndRef} />
                  </Container>
                </Box>
              )}

              {/* Sticky Input Field at bottom when chatting */}
              {messages.length > 0 && (
                <Box sx={{
                  position: 'absolute',
                  bottom: 0,
                  left: 0,
                  right: 0,
                  p: 3,
                  background: 'linear-gradient(to top, rgba(9,9,11,1) 40%, rgba(9,9,11,0))',
                  display: 'flex',
                  justifyContent: 'center'
                }}>
                  <Container maxWidth="md">
                    <AIChat onAsk={handleAsk} isLoading={isLoading} value={chatInput} onChange={setChatInput} />
                  </Container>
                </Box>
              )}
            </>
          )}
        </Box>
      </Box>
    </ThemeProvider>
  );
}

export default App;
