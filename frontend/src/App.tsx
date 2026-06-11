import React, { useState, useEffect, useRef } from 'react';
import { ThemeProvider, CssBaseline, Box, Typography, Drawer, List, ListItem, ListItemButton, ListItemIcon, ListItemText, Container, Paper, Avatar } from '@mui/material';
import axios from 'axios';
import { darkTheme } from './theme';
import { AIChat } from './components/Chat/AIChat';
import { DynamicDashboard } from './components/Dashboard/DynamicDashboard';
import StorageIcon from '@mui/icons-material/Storage';
import AddBoxIcon from '@mui/icons-material/AddBox';
import DashboardIcon from '@mui/icons-material/Dashboard';
import PersonIcon from '@mui/icons-material/Person';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import { Select, MenuItem, FormControl, InputLabel, Table, TableBody, TableCell, TableContainer, TableHead, TableRow } from '@mui/material';

const DRAWER_WIDTH = 260;
const API_URL = 'http://localhost:8001';

interface ChatMessage {
  id: string;
  role: 'user' | 'ai';
  text: string;
  dashboardData?: any;
}

function App() {
  const [isLoading, setIsLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [recents, setRecents] = useState<string[]>([]);
  const messagesEndRef = useRef<null | HTMLDivElement>(null);
  const [connections, setConnections] = useState<any[]>([]);
  const [selectedConnectionId, setSelectedConnectionId] = useState<number>(1);
  const [viewMode, setViewMode] = useState<'chat' | 'dashboard'>('chat');
  const [dashboardSearch, setDashboardSearch] = useState('');
  const [dashboardData, setDashboardData] = useState<any | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    axios.get(`${API_URL}/erp/connections`).then(res => {
      setConnections(res.data);
      if (res.data.length > 0) {
        // Default to the highest ID (most recently added) connection like Tradeware
        setSelectedConnectionId(res.data[res.data.length - 1].id);
      }
    }).catch(console.error);
  }, []);

  const handleAsk = async (question: string) => {
    const userMsg: ChatMessage = { id: Date.now().toString(), role: 'user', text: question };
    setMessages(prev => [...prev, userMsg]);
    setIsLoading(true);
    
    // Add to recents if it's the first message
    if (messages.length === 0) {
      setRecents(prev => [question.substring(0, 30) + (question.length > 30 ? '...' : ''), ...prev]);
    }

    try {
      const response = await axios.post(`${API_URL}/chat/ask`, {
        connection_id: selectedConnectionId, 
        question: question
      });
      
      const aiMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'ai',
        text: response.data.summary || "Here is the data you requested:",
        dashboardData: response.data
      };
      setMessages(prev => [...prev, aiMsg]);
      
    } catch (error: any) {
      console.error(error);
      const errorText = error.response?.data?.detail || "Sorry, I couldn't connect to the ERP database or generate the query.";
      const aiErrorMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'ai',
        text: `Error: ${errorText}`
      };
      setMessages(prev => [...prev, aiErrorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDashboardAsk = async (question: string) => {
    setIsLoading(true);
    try {
      const response = await axios.post(`${API_URL}/chat/ask`, {
        connection_id: selectedConnectionId, 
        question: question,
        view_mode: 'dashboard'
      });
      setDashboardData(response.data);
    } catch (error: any) {
      console.error(error);
      setDashboardData({ error: error.response?.data?.detail || "Error generating dashboard" });
    } finally {
      setIsLoading(false);
    }
  };

  const resetChat = () => {
    setMessages([]);
    setViewMode('chat');
  };

  const renderSimpleTable = (data: any[]) => {
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
                <TableCell colSpan={keys.length} align="center" sx={{ color: 'text.secondary', py: 1 }}>
                  ... and {data.length - 10} more rows (view in Dashboard for full data)
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    );
  };

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
          <Box sx={{ p: 3 }}>
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
                  {recents.map((text, index) => (
                    <ListItem key={index} disablePadding>
                      <ListItemButton 
                        sx={{ 
                          borderRadius: 2, 
                          mb: 0.5, 
                          py: 0.75, 
                          '&:hover': { backgroundColor: '#2A2B32' }
                        }}
                      >
                        <ListItemText 
                          primary={
                            <Typography sx={{ 
                              color: '#D1D5DB', 
                              fontSize: '0.85rem',
                              whiteSpace: 'nowrap',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis'
                            }}>
                              {text}
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
                  <AIChat onAsk={handleDashboardAsk} isLoading={isLoading} />
                </Box>
                
                {dashboardData?.error && (
                  <Paper sx={{ p: 3, bgcolor: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.2)' }}>
                    <Typography color="error">{dashboardData.error}</Typography>
                  </Paper>
                )}
                
                {dashboardData && !dashboardData.error && dashboardData.data && dashboardData.data.length > 0 && (
                  <DynamicDashboard result={dashboardData} />
                )}
                
                {!dashboardData && !isLoading && (
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
                    <AIChat onAsk={handleAsk} isLoading={isLoading} />
                  </Box>
                </Container>
              ) : (
                // Chat History State
                <Box sx={{ flexGrow: 1, overflowY: 'auto', pb: 15, pt: 4 }}>
                  <Container maxWidth="md">
                    {messages.map((msg) => (
                      <Box key={msg.id} sx={{ display: 'flex', mb: 4, gap: 2 }}>
                        <Avatar sx={{ bgcolor: msg.role === 'ai' ? 'primary.main' : 'grey.800' }}>
                          {msg.role === 'ai' ? <AutoAwesomeIcon /> : <PersonIcon />}
                        </Avatar>
                        <Box sx={{ flexGrow: 1, pt: 1 }}>
                          <Typography variant="body1" sx={{ fontWeight: msg.role === 'user' ? 500 : 400, color: 'text.primary', whiteSpace: 'pre-wrap' }}>
                            {msg.text}
                          </Typography>
                        </Box>
                      </Box>
                    ))}
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
                    <AIChat onAsk={handleAsk} isLoading={isLoading} />
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
