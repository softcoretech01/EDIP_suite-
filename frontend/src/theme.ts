import { createTheme } from '@mui/material/styles';

export const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#00F0FF', // Electric Cyan
      light: '#80F8FF',
      dark: '#00A8B2',
    },
    secondary: {
      main: '#B026FF', // Neon Violet
      light: '#D893FF',
      dark: '#7B1AB2',
    },
    background: {
      default: '#09090b', // Obsidian Black
      paper: 'rgba(255, 255, 255, 0.03)', // Premium glassmorphism base
    },
    text: {
      primary: '#F8FAFC',
      secondary: '#94A3B8',
    },
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    h1: {
      fontFamily: '"Outfit", sans-serif',
      fontWeight: 800,
      letterSpacing: '-0.03em',
    },
    h2: {
      fontFamily: '"Outfit", sans-serif',
      fontWeight: 700,
      letterSpacing: '-0.02em',
    },
    h3: {
      fontFamily: '"Outfit", sans-serif',
      fontWeight: 700,
      letterSpacing: '-0.02em',
    },
    h4: {
      fontFamily: '"Outfit", sans-serif',
      fontWeight: 600,
      letterSpacing: '-0.01em',
    },
    h5: {
      fontFamily: '"Outfit", sans-serif',
      fontWeight: 600,
    },
    h6: {
      fontFamily: '"Outfit", sans-serif',
      fontWeight: 500,
    },
    button: {
      fontFamily: '"Outfit", sans-serif',
      fontWeight: 600,
    }
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 12,
          textTransform: 'none',
          padding: '10px 24px',
          transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          '&:hover': {
            transform: 'translateY(-2px)',
            boxShadow: '0 8px 20px rgba(0, 240, 255, 0.25)',
          },
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backdropFilter: 'blur(16px)',
          WebkitBackdropFilter: 'blur(16px)',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          borderRadius: 24,
          boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)',
        },
      },
    },
  },
});
