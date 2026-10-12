import { createTheme } from '@mui/material/styles';

export const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#38BDF8', // Sky 400
      light: '#7DD3FC',
      dark: '#0284C7',
      contrastText: '#0F172A',
    },
    secondary: {
      main: '#818CF8', // Indigo 400
      light: '#A5B4FC',
      dark: '#4F46E5',
    },
    background: {
      default: '#0B0F19', // Deep dark slate
      paper: '#111827',   // Slate 900
    },
    text: {
      primary: '#F3F4F6',
      secondary: '#9CA3AF',
    },
    divider: 'rgba(255, 255, 255, 0.08)',
  },
  typography: {
    fontFamily: [
      '-apple-system',
      'BlinkMacSystemFont',
      '"Segoe UI"',
      'Roboto',
      '"Helvetica Neue"',
      'Arial',
      'sans-serif',
    ].join(','),
    h6: {
      fontWeight: 600,
      letterSpacing: '-0.02em',
    },
    subtitle1: {
      fontWeight: 500,
    },
    button: {
      textTransform: 'none',
      fontWeight: 600,
    },
    caption: {
      fontSize: '0.75rem',
    },
  },
  shape: {
    borderRadius: 10,
  },
  components: {
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          backgroundColor: '#111827',
          border: '1px solid rgba(255, 255, 255, 0.08)',
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          padding: '8px 18px',
        },
        containedPrimary: {
          background: 'linear-gradient(135deg, #0284C7 0%, #0369A1 100%)',
          boxShadow: '0 4px 14px 0 rgba(2, 132, 199, 0.35)',
          '&:hover': {
            background: 'linear-gradient(135deg, #0369A1 0%, #075985 100%)',
          },
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 12,
          border: '1px solid rgba(255, 255, 255, 0.08)',
          backgroundColor: '#111827',
          transition: 'all 0.2s ease-in-out',
        },
      },
    },
  },
});
