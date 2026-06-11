import React, { useState } from 'react';
import { Box, InputBase, IconButton, Paper, Typography, CircularProgress } from '@mui/material';
import SendIcon from '@mui/icons-material/Send';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';

interface AIChatProps {
  onAsk: (question: string) => Promise<void>;
  isLoading: boolean;
}

export const AIChat: React.FC<AIChatProps> = ({ onAsk, isLoading }) => {
  const [question, setQuestion] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (question.trim() && !isLoading) {
      onAsk(question);
      setQuestion('');
    }
  };

  return (
    <Paper 
      elevation={0} 
      sx={{ 
        p: 1.5, 
        px: 3,
        display: 'flex', 
        alignItems: 'center', 
        gap: 2,
        background: 'rgba(255, 255, 255, 0.03)',
        border: '1px solid rgba(255, 255, 255, 0.08)',
        backdropFilter: 'blur(24px)',
        borderRadius: 8,
        transition: 'all 0.3s ease',
        boxShadow: question.trim() ? '0 0 20px rgba(0, 240, 255, 0.15)' : '0 4px 24px rgba(0,0,0,0.4)',
        '&:hover': {
          border: '1px solid rgba(0, 240, 255, 0.3)',
        },
        '&:focus-within': {
          border: '1px solid rgba(0, 240, 255, 0.6)',
          boxShadow: '0 0 30px rgba(0, 240, 255, 0.2)',
        }
      }}
    >
      <AutoAwesomeIcon sx={{ color: '#00F0FF', filter: 'drop-shadow(0 0 8px rgba(0,240,255,0.8))' }} />
      <Box component="form" onSubmit={handleSubmit} sx={{ flexGrow: 1, display: 'flex', alignItems: 'center' }}>
        <InputBase
          fullWidth
          placeholder="Ask anything about your ERP data..."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={isLoading}
          sx={{ 
            color: 'text.primary', 
            fontSize: '1.1rem',
            fontFamily: '"Inter", sans-serif',
            '& input::placeholder': {
              color: 'rgba(255,255,255,0.3)',
              opacity: 1
            }
          }}
        />
        <IconButton 
          type="submit" 
          disabled={!question.trim() || isLoading}
          sx={{
            background: question.trim() && !isLoading ? 'linear-gradient(45deg, #00F0FF, #B026FF)' : 'transparent',
            color: question.trim() && !isLoading ? '#000' : 'rgba(255,255,255,0.2)',
            transition: 'all 0.3s ease',
            '&:hover': {
              background: question.trim() && !isLoading ? 'linear-gradient(45deg, #80F8FF, #D893FF)' : 'transparent',
              transform: 'scale(1.1)'
            }
          }}
        >
          {isLoading ? <CircularProgress size={24} sx={{ color: '#00F0FF' }} /> : <SendIcon />}
        </IconButton>
      </Box>
    </Paper>
  );
};
