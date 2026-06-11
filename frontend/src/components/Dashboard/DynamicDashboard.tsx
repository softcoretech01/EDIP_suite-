import React from 'react';
import { Box, Paper, Typography, Table, TableBody, TableCell, TableContainer, TableHead, TableRow } from '@mui/material';
import { BarChart, Bar, LineChart, Line, PieChart, Pie, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';

interface DashboardData {
  summary: string;
  sql: string;
  chart_type: string;
  data: any[];
}

interface DynamicDashboardProps {
  result: DashboardData | null;
}

const COLORS = ['#6C63FF', '#00E5FF', '#FF6584', '#FFD166', '#06D6A0'];

export const DynamicDashboard: React.FC<DynamicDashboardProps> = ({ result }) => {
  if (!result) return null;

  const renderChart = () => {
    if (!result.data || result.data.length === 0) return <Typography>No data to display.</Typography>;

    const keys = Object.keys(result.data[0]);
    const xKey = keys[0];
    const yKeys = keys.slice(1);

    switch (result.chart_type?.toLowerCase()) {
      case 'barchart':
      case 'bar':
        return (
          <ResponsiveContainer width="100%" height={400}>
            <BarChart data={result.data}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis dataKey={xKey} stroke="#9CA3AF" />
              <YAxis stroke="#9CA3AF" />
              <Tooltip contentStyle={{ backgroundColor: '#1F2937', border: 'none', borderRadius: 8 }} />
              {yKeys.map((key, index) => (
                <Bar key={key} dataKey={key} fill={COLORS[index % COLORS.length]} radius={[4, 4, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        );
      case 'linechart':
      case 'line':
        return (
          <ResponsiveContainer width="100%" height={400}>
            <LineChart data={result.data}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis dataKey={xKey} stroke="#9CA3AF" />
              <YAxis stroke="#9CA3AF" />
              <Tooltip contentStyle={{ backgroundColor: '#1F2937', border: 'none', borderRadius: 8 }} />
              {yKeys.map((key, index) => (
                <Line key={key} type="monotone" dataKey={key} stroke={COLORS[index % COLORS.length]} strokeWidth={3} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        );
      case 'piechart':
      case 'pie':
        return (
          <ResponsiveContainer width="100%" height={400}>
            <PieChart>
              <Tooltip contentStyle={{ backgroundColor: '#1F2937', border: 'none', borderRadius: 8 }} />
              <Pie data={result.data} dataKey={yKeys[0]} nameKey={xKey} cx="50%" cy="50%" outerRadius={150} label>
                {result.data.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        );
      default:
        // Default to Table
        return (
          <TableContainer component={Paper} sx={{ bgcolor: 'transparent', backgroundImage: 'none', boxShadow: 'none' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  {keys.map((key) => (
                    <TableCell key={key} sx={{ color: 'text.secondary', fontWeight: 'bold', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                      {key.toUpperCase()}
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {result.data.map((row, i) => (
                  <TableRow key={i}>
                    {keys.map((key) => (
                      <TableCell key={key} sx={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                        {row[key]}
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

  return (
    <Box sx={{ mt: 4, display: 'flex', flexDirection: 'column', gap: 3 }}>
      <Paper sx={{ p: 3, background: 'rgba(108, 99, 255, 0.1)', borderColor: 'primary.main' }}>
        <Typography variant="h6" color="primary.light" gutterBottom>
          AI Analysis
        </Typography>
        <Typography variant="body1">{result.summary}</Typography>
      </Paper>

      <Paper sx={{ p: 3, flexGrow: 1, minHeight: 400 }}>
        <Typography variant="h6" gutterBottom>
          Data Visualization
        </Typography>
        {renderChart()}
      </Paper>
      
      <Paper sx={{ p: 2, bgcolor: 'rgba(0,0,0,0.2)' }}>
        <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
          Generated SQL: {result.sql}
        </Typography>
      </Paper>
    </Box>
  );
};
