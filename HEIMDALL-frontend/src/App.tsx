import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { useState } from 'react';
import Layout            from '@/components/layout/Layout';
import DashboardPage     from '@/pages/DashboardPage';
import NewScreeningPage  from '@/pages/NewScreeningPage';
import ScreeningResultPage from '@/pages/ScreeningResultPage';
import HistoryPage       from '@/pages/HistoryPage';
import AnalyticsPage     from '@/pages/AnalyticsPage';
import LoginPage         from '@/pages/LoginPage';

const TOKEN_KEY = 'heimdall_token';

export default function App() {
  const [authed, setAuthed] = useState<boolean>(() => !!localStorage.getItem(TOKEN_KEY));

  return (
    <>
      <Toaster position="top-right" toastOptions={{
        style: { background:'#fff', color:'#111827', border:'1px solid #e5e7eb', fontSize:13 },
      }}/>
      {authed ? (
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Layout />}>
              <Route index element={<Navigate to="/dashboard" replace />} />
              <Route path="dashboard"        element={<DashboardPage />} />
              <Route path="screening/new"    element={<NewScreeningPage />} />
              <Route path="screening/:id"    element={<ScreeningResultPage />} />
              <Route path="history"          element={<HistoryPage />} />
              <Route path="analytics"        element={<AnalyticsPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      ) : (
        <LoginPage onDone={() => setAuthed(true)} />
      )}
    </>
  );
}
