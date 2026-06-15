import React, { useState, useRef } from 'react';
import { Box, InputBase, IconButton, Paper, Typography, CircularProgress } from '@mui/material';
import SendIcon from '@mui/icons-material/Send';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import AttachFileIcon from '@mui/icons-material/AttachFile';

interface AIChatProps {
  onAsk: (question: string) => Promise<void>;
  isLoading: boolean;
  value?: string;
  onChange?: (value: string) => void;
  clearOnSubmit?: boolean;
  onUpload?: (file: File) => Promise<void>;
  isUploading?: boolean;
}

export const AIChat: React.FC<AIChatProps> = ({ 
  onAsk, 
  isLoading, 
  value, 
  onChange, 
  clearOnSubmit = true,
  onUpload,
  isUploading = false
}) => {
  const [localQuestion, setLocalQuestion] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  const question = value !== undefined ? value : localQuestion;
  const setQuestion = onChange || setLocalQuestion;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (question.trim() && !isLoading) {
      onAsk(question);
      if (clearOnSubmit) {
        setQuestion('');
      }
    }
  };

  const handleAttachClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && onUpload) {
      onUpload(file);
    }
    // Reset the value so that uploading the same file again triggers change
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
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
      
      {onUpload && (
        <>
          <input 
            type="file" 
            ref={fileInputRef} 
            style={{ display: 'none' }} 
            onChange={handleFileChange}
            accept=".xlsx,.xls,.docx,.pdf,.txt,.csv"
          />
          <IconButton 
            onClick={handleAttachClick}
            disabled={isUploading || isLoading}
            sx={{
              color: 'rgba(255,255,255,0.5)',
              '&:hover': {
                color: '#00F0FF',
                background: 'rgba(0, 240, 255, 0.05)'
              }
            }}
          >
            {isUploading ? (
              <CircularProgress size={20} sx={{ color: '#00F0FF' }} />
            ) : (
              <AttachFileIcon />
            )}
          </IconButton>
        </>
      )}

      <Box component="form" onSubmit={handleSubmit} sx={{ flexGrow: 1, display: 'flex', alignItems: 'center' }}>
        <InputBase
          fullWidth
          placeholder="Ask anything about ERP, or type keywords to query uploaded documents/sheets..."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={isLoading || isUploading}
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
          disabled={!question.trim() || isLoading || isUploading}
          sx={{
            background: question.trim() && !isLoading && !isUploading ? 'linear-gradient(45deg, #00F0FF, #B026FF)' : 'transparent',
            color: question.trim() && !isLoading && !isUploading ? '#000' : 'rgba(255,255,255,0.2)',
            transition: 'all 0.3s ease',
            '&:hover': {
              background: question.trim() && !isLoading && !isUploading ? 'linear-gradient(45deg, #80F8FF, #D893FF)' : 'transparent',
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

