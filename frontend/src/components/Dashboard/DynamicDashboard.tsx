import React from 'react';
import { Box, Paper, Typography, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Grid, Card, Divider } from '@mui/material';
import { BarChart, Bar, LineChart, Line, PieChart, Pie, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import AssessmentIcon from '@mui/icons-material/Assessment';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import FormatQuoteIcon from '@mui/icons-material/FormatQuote';
import LightbulbIcon from '@mui/icons-material/Lightbulb';
import TrackChangesIcon from '@mui/icons-material/TrackChanges';
import TableViewIcon from '@mui/icons-material/TableView';

export interface DashboardData {
  summary?: string;
  executive_summary?: string;
  business_insights?: string[];
  recommendations?: string[];
  sql?: string;
  chart_type?: string;
  data?: any[];
  error?: string;
}

interface DynamicDashboardProps {
  result: DashboardData | null;
}

const COLORS = ['#3B82F6', '#22C55E', '#F59E0B', '#8B5CF6', '#EC4899'];

const formatValue = (key: string, value: any, isCard = false) => {
  if (value === null || value === undefined) return isCard ? '0' : '-';
  const numValue = Number(value);
  const isNumeric = !isNaN(numValue) && typeof value !== 'boolean' && value !== '';
  
  const keyLower = key.toLowerCase();
  const isQuantityOrCount = keyLower.includes('qty') || keyLower.includes('quantity') || keyLower.includes('count') || keyLower.includes('item') || keyLower.includes('order') || keyLower.includes('invoice') || keyLower.includes('customer') || keyLower.includes('supplier') || keyLower.includes('user') || keyLower.includes('schedule') || keyLower.includes('id');
  const isCurrency = (
    keyLower.includes('amount') || 
    keyLower.includes('total') || 
    keyLower.includes('price') || 
    keyLower.includes('cost') || 
    keyLower.includes('val') || 
    keyLower.includes('fcy') || 
    keyLower.includes('lcy')
  ) && !isQuantityOrCount;

  if (isNumeric && isCurrency) {
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(numValue);
  }
  
  return String(value);
};

export const DynamicDashboard: React.FC<DynamicDashboardProps> = ({ result }) => {
  if (!result) return null;

  // Render Error Mode
  if (result.error) {
    return (
      <Paper sx={{ 
        p: 4, 
        bgcolor: '#1E293B', 
        borderRadius: 4, 
        border: '1px solid rgba(245, 158, 11, 0.3)',
        boxShadow: '0 0 30px rgba(245, 158, 11, 0.1)',
        backdropFilter: 'blur(10px)',
        animation: 'fadeIn 0.5s ease-out'
      }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 3, gap: 2 }}>
          <WarningAmberIcon sx={{ color: '#F59E0B', fontSize: 40 }} />
          <Typography variant="h5" sx={{ color: '#F59E0B', fontWeight: 700 }}>
            Unable to retrieve information
          </Typography>
        </Box>
        <Typography sx={{ color: 'text.secondary', mb: 4, fontSize: '1.1rem' }}>
          {result.error}
        </Typography>
        <Box sx={{ p: 2, bgcolor: 'rgba(0,0,0,0.3)', borderRadius: 2, border: '1px dashed rgba(255,255,255,0.1)' }}>
          <Typography variant="caption" sx={{ color: '#64748B', fontFamily: 'monospace' }}>
            Reference ID: EDIP-ERR-001
          </Typography>
        </Box>
      </Paper>
    );
  }

  // Safe checks
  const data = result.data || [];
  const execSummary = result.executive_summary || result.summary || "Analysis complete.";
  const insights = result.business_insights || [];
  const recs = result.recommendations || [];

  const renderChart = () => {
    if (data.length === 0) return <Typography sx={{ color: 'text.secondary' }}>No data to display.</Typography>;

    const keys = Object.keys(data[0]);
    const xKey = keys[0];
    const yKeys = keys.slice(1);

    switch (result.chart_type?.toLowerCase()) {
      case 'barchart':
      case 'bar':
        return (
          <ResponsiveContainer width="100%" height={350}>
            <BarChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey={xKey} stroke="#64748B" />
              <YAxis stroke="#64748B" />
              <Tooltip formatter={(value: any, name: any) => [formatValue(String(name), value), name]} contentStyle={{ backgroundColor: '#0F172A', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, color: '#fff' }} />
              {yKeys.map((key, index) => (
                <Bar key={key} dataKey={key} fill={COLORS[index % COLORS.length]} radius={[4, 4, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        );
      case 'linechart':
      case 'line':
        return (
          <ResponsiveContainer width="100%" height={350}>
            <LineChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey={xKey} stroke="#64748B" />
              <YAxis stroke="#64748B" />
              <Tooltip formatter={(value: any, name: any) => [formatValue(String(name), value), name]} contentStyle={{ backgroundColor: '#0F172A', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, color: '#fff' }} />
              {yKeys.map((key, index) => (
                <Line key={key} type="monotone" dataKey={key} stroke={COLORS[index % COLORS.length]} strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 8 }} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        );
      case 'piechart':
      case 'pie':
        return (
          <ResponsiveContainer width="100%" height={350}>
            <PieChart>
              <Tooltip formatter={(value: any, name: any) => [formatValue(String(name), value), name]} contentStyle={{ backgroundColor: '#0F172A', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, color: '#fff' }} />
              <Pie data={data} dataKey={yKeys[0] || keys[0]} nameKey={xKey} cx="50%" cy="50%" outerRadius={120} label>
                {data.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        );
      case 'card':
      case 'metric':
        return null; // Rendered in Key Metrics section instead
      default:
        // Default to Table
        return (
          <TableContainer sx={{ maxHeight: 400, '&::-webkit-scrollbar': { width: '8px', height: '8px' }, '&::-webkit-scrollbar-thumb': { backgroundColor: 'rgba(255,255,255,0.2)', borderRadius: '4px' } }}>
            <Table stickyHeader size="small">
              <TableHead>
                <TableRow>
                  {keys.map((key) => (
                    <TableCell key={key} sx={{ bgcolor: '#0F172A', color: '#94A3B8', fontWeight: 600, borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                      {key.replace(/_/g, ' ').toUpperCase()}
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {data.map((row, i) => (
                  <TableRow key={i} sx={{ '&:hover': { bgcolor: 'rgba(255,255,255,0.02)' } }}>
                    {keys.map((key) => (
                      <TableCell key={key} sx={{ color: '#E2E8F0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                        {formatValue(key, row[key])}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        );
    }
  };

  const isCardType = result.chart_type?.toLowerCase() === 'card' || result.chart_type?.toLowerCase() === 'metric';

  return (
    <Paper sx={{ 
      p: { xs: 3, md: 5 }, 
      bgcolor: '#1E293B', 
      borderRadius: 4, 
      border: '1px solid rgba(59, 130, 246, 0.3)',
      boxShadow: '0 0 20px rgba(59, 130, 246, 0.1)',
      backdropFilter: 'blur(10px)',
      animation: 'fadeIn 0.5s ease-out',
      '@keyframes fadeIn': {
        from: { opacity: 0, transform: 'translateY(10px)' },
        to: { opacity: 1, transform: 'translateY(0)' }
      }
    }}>
      {/* 5. AI Branding Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 4, pb: 3, borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        <Box sx={{ bgcolor: 'rgba(59, 130, 246, 0.1)', p: 1.5, borderRadius: 3, mr: 3 }}>
          <AutoAwesomeIcon sx={{ color: '#3B82F6', fontSize: 32 }} />
        </Box>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 800, color: '#F8FAFC', letterSpacing: 0.5 }}>
            EDIP AI Analyst
          </Typography>
          <Typography variant="subtitle2" sx={{ color: '#3B82F6', fontWeight: 600, letterSpacing: 1 }}>
            Executive Decision Intelligence Platform • <span style={{ color: '#94A3B8' }}>Ask. Analyze. Visualize.</span>
          </Typography>
        </Box>
      </Box>

      {/* 1. EXECUTIVE SUMMARY */}
      <Box sx={{ mb: 5 }}>
        <Typography variant="subtitle1" sx={{ color: '#94A3B8', fontWeight: 700, mb: 1, display: 'flex', alignItems: 'center', letterSpacing: 1 }}>
          <FormatQuoteIcon sx={{ mr: 1, fontSize: 20 }} /> EXECUTIVE SUMMARY
        </Typography>
        <Typography variant="h6" sx={{ color: '#F1F5F9', fontWeight: 400, fontStyle: 'italic', pl: 4, borderLeft: '3px solid #3B82F6' }}>
          "{execSummary}"
        </Typography>
      </Box>

      {/* 2. KEY METRICS */}
      {isCardType && data.length > 0 && (
        <Box sx={{ mb: 5 }}>
          <Typography variant="subtitle1" sx={{ color: '#94A3B8', fontWeight: 700, mb: 3, display: 'flex', alignItems: 'center', letterSpacing: 1 }}>
            <AssessmentIcon sx={{ mr: 1, fontSize: 20 }} /> KEY METRICS
          </Typography>
          <Grid container spacing={3}>
            {data.map((row, rowIndex) => 
              Object.keys(row).map((key, colIndex) => (
                <Grid item xs={12} sm={6} md={Object.keys(row).length === 1 ? 12 : 4} key={`${rowIndex}-${key}`}>
                  <Card sx={{ 
                    bgcolor: '#0F172A', 
                    borderRadius: 3, 
                    boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
                    display: 'flex',
                    alignItems: 'center',
                    p: 3,
                    border: '1px solid rgba(255,255,255,0.05)',
                    position: 'relative',
                    overflow: 'hidden'
                  }}>
                    {/* Decorative accent line */}
                    <Box sx={{ position: 'absolute', top: 0, left: 0, width: '4px', height: '100%', bgcolor: COLORS[colIndex % COLORS.length] }} />
                    <Box>
                      <Typography sx={{ color: '#94A3B8', fontWeight: 600, fontSize: '0.85rem', mb: 1, letterSpacing: 1 }}>
                        {key.replace(/_/g, ' ').toUpperCase()}
                      </Typography>
                      <Typography variant={Object.keys(row).length === 1 ? 'h2' : 'h4'} sx={{ fontWeight: 800, color: '#F8FAFC' }}>
                        {formatValue(key, row[key], true)}
                      </Typography>
                    </Box>
                  </Card>
                </Grid>
              ))
            )}
          </Grid>
        </Box>
      )}

      {/* 3. BUSINESS INSIGHTS */}
      {insights.length > 0 && (
        <Box sx={{ mb: 5 }}>
          <Typography variant="subtitle1" sx={{ color: '#94A3B8', fontWeight: 700, mb: 2, display: 'flex', alignItems: 'center', letterSpacing: 1 }}>
            <LightbulbIcon sx={{ mr: 1, fontSize: 20, color: '#F59E0B' }} /> BUSINESS INSIGHTS
          </Typography>
          <Box sx={{ pl: 2 }}>
            {insights.map((insight, idx) => (
              <Box key={idx} sx={{ display: 'flex', mb: 1.5, alignItems: 'flex-start' }}>
                <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: '#3B82F6', mt: 1, mr: 2, flexShrink: 0 }} />
                <Typography sx={{ color: '#E2E8F0', fontSize: '1.05rem' }}>{insight}</Typography>
              </Box>
            ))}
          </Box>
        </Box>
      )}

      {/* 4. RECOMMENDATIONS */}
      {recs.length > 0 && (
        <Box sx={{ mb: 5 }}>
          <Typography variant="subtitle1" sx={{ color: '#94A3B8', fontWeight: 700, mb: 2, display: 'flex', alignItems: 'center', letterSpacing: 1 }}>
            <TrackChangesIcon sx={{ mr: 1, fontSize: 20, color: '#22C55E' }} /> RECOMMENDATIONS
          </Typography>
          <Box sx={{ pl: 2 }}>
            {recs.map((rec, idx) => (
              <Box key={idx} sx={{ display: 'flex', mb: 1.5, alignItems: 'flex-start' }}>
                <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: '#22C55E', mt: 1, mr: 2, flexShrink: 0 }} />
                <Typography sx={{ color: '#E2E8F0', fontSize: '1.05rem' }}>{rec}</Typography>
              </Box>
            ))}
          </Box>
        </Box>
      )}

      {/* 5. DETAILS (CHARTS / TABLES) */}
      {!isCardType && data.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="subtitle1" sx={{ color: '#94A3B8', fontWeight: 700, mb: 3, display: 'flex', alignItems: 'center', letterSpacing: 1 }}>
            <TableViewIcon sx={{ mr: 1, fontSize: 20 }} /> {result.chart_type === 'table' || !result.chart_type ? 'DETAILED RECORDS' : 'DATA VISUALIZATION'}
          </Typography>
          <Paper sx={{ p: 3, bgcolor: '#0F172A', borderRadius: 3, border: '1px solid rgba(255,255,255,0.05)' }}>
            {renderChart()}
          </Paper>
        </Box>
      )}

    </Paper>
  );
};
